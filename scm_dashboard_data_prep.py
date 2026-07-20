# -*- coding: utf-8 -*-
"""
AS-IS/TO-BE HTML 대시보드용 데이터 취합 -> dashboard_data.json
"""
import json
import numpy as np
import pandas as pd

import scm_inventory_analysis as base

df = base.df
panel = base.panel.copy()
cs = base.cs.copy()
CENTER_REGION = base.CENTER_REGION
CENTERS = [1, 2, 3, 4, 5]
CAPA = dict(zip(cs["센터"], cs["Capa_kg"]))
OUT_TOTAL = dict(zip(cs["센터"], cs["출고합_kg"]))

STORAGE_SUPPORT = {1: {"실온", "냉동", "냉장"}, 2: {"실온", "냉동", "냉장"}, 3: {"냉동"},
                   4: {"실온", "냉동", "냉장"}, 5: {"실온", "냉동", "냉장"}}

tobe = pd.read_csv(r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\tobe_allocation_LP.csv")
tobe["inc_kg"] = tobe["변화_kg"].clip(lower=0)

info = df[["상품 정보_상품코드", "상품 정보_상품명", "상품 정보_상품범주", "상품 정보_저장조건"]].rename(
    columns={"상품 정보_상품코드": "sku_id", "상품 정보_상품명": "sku_name",
             "상품 정보_상품범주": "category", "상품 정보_저장조건": "storage_type"})
tobe = tobe.merge(info[["sku_id", "sku_name", "category"]], on="sku_id", how="left")

# ============================================================
# [A] 센터별 AS-IS vs TO-BE
# ============================================================
tobe_stock_by_center = tobe.groupby("center_id")["TO_BE_stock_kg"].sum()

def status_of(days, mean_days):
    if days > mean_days * 1.3:
        return "과적재"
    if days < mean_days * 0.5:
        return "저활용"
    return "정상"

center_rows = []
for c in CENTERS:
    asis_stock = float(cs.loc[cs["센터"] == c, "재고합_kg"].values[0])
    tobe_stock = float(tobe_stock_by_center.get(c, 0.0))
    capa = float(CAPA[c])
    out_kg = float(OUT_TOTAL[c])
    asis_days = asis_stock / (out_kg / 30)
    tobe_days = tobe_stock / (out_kg / 30)
    center_rows.append({
        "center": c, "region": CENTER_REGION[c],
        "asis_stock_kg": round(asis_stock), "tobe_stock_kg": round(tobe_stock),
        "capa_kg": round(capa),
        "asis_util_pct": round(asis_stock / capa * 100, 1),
        "tobe_util_pct": round(tobe_stock / capa * 100, 1),
        "asis_days": round(asis_days, 2), "tobe_days": round(tobe_days, 2),
    })
mean_days_asis = float(np.mean([r["asis_days"] for r in center_rows]))
mean_days_tobe = float(np.mean([r["tobe_days"] for r in center_rows]))
for r in center_rows:
    r["asis_status"] = status_of(r["asis_days"], mean_days_asis)
    r["tobe_status"] = status_of(r["tobe_days"], mean_days_tobe)

gap_asis = max(r["asis_days"] for r in center_rows) - min(r["asis_days"] for r in center_rows)
gap_tobe = max(r["tobe_days"] for r in center_rows) - min(r["tobe_days"] for r in center_rows)

# 실제 극단 센터(최대/최소 회전일수) 자동 식별 - 하드코딩하지 않음
over_center = max(center_rows, key=lambda r: r["asis_days"])
under_center = min(center_rows, key=lambda r: r["asis_days"])

# ============================================================
# [B] 저장조건별 AS-IS vs TO-BE
# ============================================================
storage_map = df.set_index("상품 정보_상품코드")["상품 정보_저장조건"]
panel["저장조건"] = panel["상품코드"].map(storage_map)
tobe["storage_type"] = tobe["sku_id"].map(storage_map)

valid_asis = panel["재고량_kg"] > 0
th_asis = panel.loc[valid_asis, "회전율_kg(출고kg/재고kg)"].quantile(0.20)
panel["악성재고_AS_IS"] = valid_asis & (panel["회전율_kg(출고kg/재고kg)"] <= th_asis) & (panel["이체유입_kg"] > 0)

out_wide = pd.DataFrame({"sku_id": df["상품 정보_상품코드"]}).assign(**{f"out_{c}": df[base.OUT_COLS[c]] for c in CENTERS})
tobe = tobe.merge(out_wide, on="sku_id", how="left")
tobe["out_kg"] = tobe.apply(lambda r: r[f"out_{int(r['center_id'])}"], axis=1)
valid_tobe = tobe["TO_BE_stock_kg"] > 0
tobe["turnover_tobe"] = np.where(valid_tobe, tobe["out_kg"] / tobe["TO_BE_stock_kg"], np.nan)
th_tobe = tobe.loc[valid_tobe, "turnover_tobe"].quantile(0.20)
tobe["악성재고_TO_BE"] = valid_tobe & (tobe["turnover_tobe"] <= th_tobe) & (tobe["inc_kg"] > 0)

storage_rows = []
for st in ["실온", "냉동", "냉장"]:
    p = panel[panel["저장조건"] == st]
    t = tobe[tobe["storage_type"] == st]
    # 재고보유일수는 셀별 비율의 평균/중앙값이 아니라 (센터 지표와 동일하게) 집계값으로 계산
    # -> 안전재고 바닥에 걸린 소수 셀의 극단적 회전율이 평균을 왜곡하는 문제를 피함
    asis_stock_sum = p["재고량_kg"].sum()
    asis_out_sum = p["월출고량_kg"].sum()
    tobe_stock_sum = t["TO_BE_stock_kg"].sum()
    tobe_out_sum = t["out_kg"].sum()
    storage_rows.append({
        "storage": st,
        "asis_days": round(asis_stock_sum / (asis_out_sum / 30), 2),
        "tobe_days": round(tobe_stock_sum / (tobe_out_sum / 30), 2),
        "asis_transfer_kg": round(p["이체유입_kg"].sum()),
        "tobe_move_kg": round(t["inc_kg"].sum()),
        "asis_bad_pct": round(p["악성재고_AS_IS"].mean() * 100, 2),
        "tobe_bad_pct": round(t["악성재고_TO_BE"].mean() * 100, 2),
    })

# ============================================================
# [C] 요약 카드
# ============================================================
bad_rows_asis = panel[panel["악성재고_AS_IS"]]
bad_pairs = set(zip(bad_rows_asis["상품코드"], bad_rows_asis["센터"]))
bad_tobe_match = tobe[tobe.apply(lambda r: (r["sku_id"], r["center_id"]) in bad_pairs, axis=1)]
asis_bad_kg = float(bad_rows_asis.merge(
    tobe[["sku_id", "center_id", "AS_IS_stock_kg"]].rename(columns={"sku_id": "상품코드", "center_id": "센터"}),
    on=["상품코드", "센터"], how="left")["재고량_kg"].sum())
tobe_bad_kg = float(bad_tobe_match["TO_BE_stock_kg"].sum())

transfer_cost = base.transfer_cost
avgcost_to = {j: float(np.mean([transfer_cost[(k, j)] for k in CENTERS if k != j])) for j in CENTERS}
asis_actual_cost = 0.0
for dest in CENTERS:
    for src in CENTERS:
        if src == dest:
            continue
        col = f"{dest}센터 필요에 따른 이체량(kg)_{src}센터"
        asis_actual_cost += df[col].sum() * transfer_cost[(src, dest)]
asis_proxy_cost = float((panel["이체유입_kg"] * panel["센터"].map(avgcost_to)).sum())
tobe_proxy_cost = float((tobe["inc_kg"] * tobe["center_id"].map(avgcost_to)).sum())

cards = {
    "unbalance": {"before": round(gap_asis, 2), "after": round(gap_tobe, 2),
                  "pct": round((1 - gap_tobe / gap_asis) * 100, 1), "unit": "일"},
    "badstock": {"before": round(asis_bad_kg), "after": round(tobe_bad_kg),
                 "pct": round((1 - tobe_bad_kg / asis_bad_kg) * 100, 1), "unit": "kg"},
    "transfer": {"before": round(asis_proxy_cost), "after": round(tobe_proxy_cost),
                 "payback_pct": round(tobe_proxy_cost / asis_proxy_cost * 100, 1)},
}

# ============================================================
# [D] SKU 이동 상세 테이블 (변화 있는 조합만)
# ============================================================
moved = tobe[tobe["변화_kg"].abs() > 0.5].copy()
moved["direction"] = np.where(moved["변화_kg"] > 0, "유입", "유출")
table_rows = moved[[
    "sku_id", "sku_name", "category", "storage_type", "center_id",
    "AS_IS_stock_kg", "TO_BE_stock_kg", "변화_kg", "direction", "악성재고_AS_IS"
]].rename(columns={
    "sku_id": "skuId", "sku_name": "skuName", "category": "category", "storage_type": "storage",
    "center_id": "center", "AS_IS_stock_kg": "asisKg", "TO_BE_stock_kg": "tobeKg",
    "변화_kg": "changeKg", "direction": "direction", "악성재고_AS_IS": "wasBad",
}).to_dict(orient="records")

# ============================================================
# [E] 현장 실행 가이드 - 자동 생성용 재료(숫자만, 문장은 JS에서 조립)
# ============================================================
def center_sku_stats(center_id, direction):
    sub = tobe[tobe["center_id"] == center_id]
    if direction == "in":
        sub = sub[sub["변화_kg"] > 0.5]
    else:
        sub = sub[sub["변화_kg"] < -0.5]
    storage_counts = sub["storage_type"].value_counts().to_dict()
    return {
        "n_sku": int(len(sub)),
        "kg": round(float(sub["변화_kg"].abs().sum())),
        "storage_counts": {k: int(v) for k, v in storage_counts.items()},
        "top_storage": max(storage_counts, key=storage_counts.get) if storage_counts else None,
    }

under_c = under_center["center"]
over_c = over_center["center"]
insights = {
    "under_center": under_center,
    "over_center": over_center,
    "under_inflow": center_sku_stats(under_c, "in"),
    "over_outflow": center_sku_stats(over_c, "out"),
    "mean_days_asis": round(mean_days_asis, 2),
    "mean_days_tobe": round(mean_days_tobe, 2),
    "payback_pct": cards["transfer"]["payback_pct"],
    "asis_monthly_cost": cards["transfer"]["before"],
    "tobe_onetime_cost": cards["transfer"]["after"],
    "badstock_pct_reduction": cards["badstock"]["pct"],
    "badstock_n_pairs": int(len(bad_pairs)),
    "top_moves": moved.reindex(moved["변화_kg"].abs().sort_values(ascending=False).index).head(5)[
        ["sku_id", "sku_name", "storage_type", "center_id", "변화_kg"]
    ].rename(columns={"sku_id": "skuId", "sku_name": "skuName", "storage_type": "storage",
                       "center_id": "center", "변화_kg": "changeKg"}).to_dict(orient="records"),
}

dashboard_data = {
    "meta": {"n_sku": 1000, "n_center": 5, "source": "25년6월이체출고실적"},
    "centers": center_rows,
    "storage": storage_rows,
    "cards": cards,
    "table": table_rows,
    "insights": insights,
}

out_path = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\dashboard_data.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(dashboard_data, f, ensure_ascii=False, default=lambda o: None)

print("saved:", out_path)
print("table rows:", len(table_rows))
print("centers:", json.dumps(center_rows, ensure_ascii=False, indent=2))
print("storage:", json.dumps(storage_rows, ensure_ascii=False, indent=2))
print("cards:", json.dumps(cards, ensure_ascii=False, indent=2))
print("insights (no top_moves):", json.dumps({k: v for k, v in insights.items() if k != "top_moves"}, ensure_ascii=False, indent=2))
print("top_moves:", json.dumps(insights["top_moves"], ensure_ascii=False, indent=2))

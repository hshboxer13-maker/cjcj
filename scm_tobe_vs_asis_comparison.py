# -*- coding: utf-8 -*-
"""
2단계 AS-IS 진단 vs 3단계 TO-BE 최적화 결과 비교
"""
import numpy as np
import pandas as pd

import scm_inventory_analysis as base

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)

df = base.df
panel = base.panel.copy()
cs = base.cs.copy()
transfer_cost = base.transfer_cost
CENTERS = [1, 2, 3, 4, 5]
CAPA = dict(zip(cs["센터"], cs["Capa_kg"]))
OUT_TOTAL = dict(zip(cs["센터"], cs["출고합_kg"]))  # TO-BE에서도 수요(고객 위치)는 불변으로 가정

tobe = pd.read_csv(r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\tobe_allocation_LP.csv")
tobe["inc_kg"] = (tobe["변화_kg"].clip(lower=0))

avgcost_to = {j: np.mean([transfer_cost[(k, j)] for k in CENTERS if k != j]) for j in CENTERS}

STORAGE_SUPPORT = {1: {"실온", "냉동", "냉장"}, 2: {"실온", "냉동", "냉장"}, 3: {"냉동"},
                   4: {"실온", "냉동", "냉장"}, 5: {"실온", "냉동", "냉장"}}

# ============================================================
# [1] 센터별 적재율 & 재고회전일수: AS-IS vs TO-BE
# ============================================================
print("=" * 90)
print("[1] 센터별 적재율 / 재고회전일수 - AS-IS vs TO-BE")
print("=" * 90)

tobe_stock_by_center = tobe.groupby("center_id")["TO_BE_stock_kg"].sum()

rows = []
for c in CENTERS:
    asis_stock = cs.loc[cs["센터"] == c, "재고합_kg"].values[0]
    tobe_stock = tobe_stock_by_center.get(c, 0.0)
    capa = CAPA[c]
    out_kg = OUT_TOTAL[c]
    rows.append({
        "센터": c,
        "AS-IS 재고(kg)": round(asis_stock),
        "TO-BE 재고(kg)": round(tobe_stock),
        "AS-IS 적재율(%)": round(asis_stock / capa * 100, 1),
        "TO-BE 적재율(%)": round(tobe_stock / capa * 100, 1),
        "AS-IS 재고회전일수": round(asis_stock / (out_kg / 30), 2),
        "TO-BE 재고회전일수": round(tobe_stock / (out_kg / 30), 2),
    })
util_df = pd.DataFrame(rows)
print(util_df.to_string(index=False))

mean_days_asis = util_df["AS-IS 재고회전일수"].mean()
mean_days_tobe = util_df["TO-BE 재고회전일수"].mean()
gap_asis = util_df["AS-IS 재고회전일수"].max() - util_df["AS-IS 재고회전일수"].min()
gap_tobe = util_df["TO-BE 재고회전일수"].max() - util_df["TO-BE 재고회전일수"].min()
c1_c3_gap_asis = abs(util_df.loc[util_df["센터"]==1,"AS-IS 재고회전일수"].values[0] - util_df.loc[util_df["센터"]==3,"AS-IS 재고회전일수"].values[0])
c1_c3_gap_tobe = abs(util_df.loc[util_df["센터"]==1,"TO-BE 재고회전일수"].values[0] - util_df.loc[util_df["센터"]==3,"TO-BE 재고회전일수"].values[0])
print(f"\n네트워크 평균 재고회전일수: AS-IS {mean_days_asis:.2f}일 -> TO-BE {mean_days_tobe:.2f}일")
print(f"센터 간 최대-최소 격차(불균형폭): AS-IS {gap_asis:.2f}일 -> TO-BE {gap_tobe:.2f}일 "
      f"({(1-gap_tobe/gap_asis)*100:.1f}% 축소)")
print(f"1센터-3센터 격차: AS-IS {c1_c3_gap_asis:.2f}일 -> TO-BE {c1_c3_gap_tobe:.2f}일 "
      f"({(1-c1_c3_gap_tobe/c1_c3_gap_asis)*100:.1f}% 축소)")

util_df.to_csv(r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\compare_center_utilization.csv", index=False, encoding="utf-8-sig")

# ============================================================
# [2] 악성재고 비중: AS-IS vs TO-BE (동일 방법론 재적용)
# ============================================================
print("\n" + "=" * 90)
print("[2] 악성재고 비중 - AS-IS vs TO-BE")
print("=" * 90)

# AS-IS 태깅 (기존 방식 재현)
valid_asis = panel["재고량_kg"] > 0
th_asis = panel.loc[valid_asis, "회전율_kg(출고kg/재고kg)"].quantile(0.20)
panel["악성재고_AS_IS"] = valid_asis & (panel["회전율_kg(출고kg/재고kg)"] <= th_asis) & (panel["이체유입_kg"] > 0)
n_bad_asis = panel["악성재고_AS_IS"].sum()

# TO-BE 태깅: 동일 정의(회전율 하위20% & 순유입>0)를 TO-BE 수치에 재적용
tobe_out = tobe.merge(
    pd.DataFrame({"sku_id": df["상품 정보_상품코드"]}).assign(**{f"out_{c}": df[base.OUT_COLS[c]] for c in CENTERS}),
    on="sku_id", how="left"
)
def pick_out(row):
    return row[f"out_{int(row['center_id'])}"]
tobe_out["out_kg"] = tobe_out.apply(pick_out, axis=1)

valid_tobe = tobe_out["TO_BE_stock_kg"] > 0
tobe_out["turnover_tobe"] = np.where(valid_tobe, tobe_out["out_kg"] / tobe_out["TO_BE_stock_kg"], np.nan)
th_tobe = tobe_out.loc[valid_tobe, "turnover_tobe"].quantile(0.20)
tobe_out["악성재고_TO_BE"] = valid_tobe & (tobe_out["turnover_tobe"] <= th_tobe) & (tobe_out["inc_kg"] > 0)
n_bad_tobe = tobe_out["악성재고_TO_BE"].sum()

n_total_asis = len(panel)
n_total_tobe = len(tobe_out)
print(f"AS-IS 악성재고: {n_bad_asis}건 / {n_total_asis}건 조합 ({n_bad_asis/n_total_asis*100:.2f}%)")
print(f"TO-BE 악성재고: {n_bad_tobe}건 / {n_total_tobe}건 조합 ({n_bad_tobe/n_total_tobe*100:.2f}%)")
print(f"개선율: {(1 - (n_bad_tobe/n_total_tobe)/(n_bad_asis/n_total_asis))*100:.1f}%")
print("  * 주의: '악성재고' 정의 자체가 '순유입(inc_kg)>0'을 요구하므로, TO-BE에서 재고가 줄어든 셀은")
print("    정의상 태깅될 수 없다 - 0%는 어느 정도 정의에 내재된 결과이며, 실질적 개선은 위 128건의")
print("    실제 감소량(다음 블록)으로 별도 확인 필요")

# 원래 128건 AS-IS 악성재고 조합이 TO-BE에서 얼마나 축소됐는지 추적
# (참고: 하드제약인 안전재고 바닥까지 밀어내리진 않음 - 이체/리드타임 페널티와 균형을 맞춘 최적해이기 때문)
bad_tobe_rows = tobe[tobe["악성재고_AS_IS"] == True].copy()
bad_tobe_rows["감소율_pct"] = -bad_tobe_rows["변화_kg"] / bad_tobe_rows["AS_IS_stock_kg"] * 100
asis_bad_kg = bad_tobe_rows["AS_IS_stock_kg"].sum()
tobe_bad_kg = bad_tobe_rows["TO_BE_stock_kg"].sum()
n_at_floor = (bad_tobe_rows["TO_BE_stock_kg"] <= bad_tobe_rows["안전재고_kg"] + 1e-6).sum()
print(f"\nAS-IS 악성재고 128건: 재고 {asis_bad_kg:,.0f}kg -> TO-BE {tobe_bad_kg:,.0f}kg ({(1-tobe_bad_kg/asis_bad_kg)*100:.1f}% 감소)")
print(f"조합별 평균 감소율: {bad_tobe_rows['감소율_pct'].mean():.1f}% (중앙값 {bad_tobe_rows['감소율_pct'].median():.1f}%)")
print(f"안전재고 하한까지 완전히 축소된 조합: {n_at_floor}건/128건 "
      f"(나머지는 이관비용·리드타임 페널티와 균형을 맞춘 지점에서 최적화됨 - 전량 이동이 항상 최선은 아님)")

# ============================================================
# [3] 이체비용/건수: AS-IS(실제 이체실적) vs TO-BE(예상), 절감률
# ============================================================
print("\n" + "=" * 90)
print("[3] 이체비용/건수 - AS-IS(실제) vs TO-BE(예상)")
print("=" * 90)

# AS-IS 실제: 원본 20개 OD쌍 컬럼 x 실제 거리기반 단가
asis_actual_cost = 0.0
for dest in CENTERS:
    for src in CENTERS:
        if src == dest:
            continue
        col = f"{dest}센터 필요에 따른 이체량(kg)_{src}센터"
        kg = df[col].sum()
        asis_actual_cost += kg * transfer_cost[(src, dest)]

# AS-IS 프록시(도착센터 평균단가 x 이체유입) - TO-BE와 동일 방법론, 공정비교용
asis_proxy_cost = sum(panel["이체유입_kg"] * panel["센터"].map(avgcost_to))
tobe_proxy_cost = float((tobe["inc_kg"] * tobe["center_id"].map(avgcost_to)).sum())

asis_txn_count = int((panel["이체유입_kg"] > 0).sum())
tobe_txn_count = int((tobe["inc_kg"] > 0).sum())

print(f"AS-IS 실제 이체비용(OD쌍 실측 x 거리기반단가, 월간 반복 발생): {asis_actual_cost:,.0f} 원/월")
print(f"AS-IS 프록시 이체비용(도착센터 평균단가 기준, 월간 반복 발생): {asis_proxy_cost:,.0f} 원/월")
print(f"TO-BE 재배치 비용(도착센터 평균단가 기준, AS-IS -> TO-BE로 전환하는 1회성 비용): {tobe_proxy_cost:,.0f} 원")
print()
print("  *** 주의: 두 수치는 성격이 다르다 ***")
print("  AS-IS는 매달 반복되는 크로스도킹/이체 운영비(월간 OPEX)이고,")
print("  TO-BE는 AS-IS 상태에서 TO-BE 목표재고로 '한 번' 재배치하는 데 드는 1회성 전환비용이다.")
print("  따라서 '94.6% 절감'처럼 직접 비교해 상시비용이 줄었다고 말하는 것은 잘못된 해석이다.")
print("  대신 '이 1회성 전환비용이 현재 월간 운영비 대비 어느 정도 규모인가(회수기간 관점)'로 해석해야 한다:")
payback_pct = tobe_proxy_cost / asis_proxy_cost * 100
print(f"  -> TO-BE 전환비용은 AS-IS 월간 반복 이체비용의 {payback_pct:.1f}% 수준")
print(f"     (안전재고 확보로 향후 월별 JIT 이체 의존도가 줄어든다면, 수 주~1개월 내 회수 가능한 투자로 해석 가능")
print(f"      단, 이는 추정이며 실제 회수기간 검증에는 TO-BE 운영 후 수개월치 실측 데이터가 필요)")
print(f"\nAS-IS 이체건수(실제 이체유입>0, 월간 반복): {asis_txn_count}건/월")
print(f"TO-BE 재배치 이동건수(1회성 순유입>0): {tobe_txn_count}건")
print(f"  -> TO-BE 1회성 이동건수는 AS-IS 월간 이체건수의 {tobe_txn_count/asis_txn_count*100:.1f}% 규모")

cost_compare = pd.DataFrame([
    {"구분": "AS-IS(실제 OD쌍)", "이체비용(원)": round(asis_actual_cost), "이체건수": asis_txn_count},
    {"구분": "AS-IS(프록시, TO-BE와 동일방법론)", "이체비용(원)": round(asis_proxy_cost), "이체건수": asis_txn_count},
    {"구분": "TO-BE(프록시)", "이체비용(원)": round(tobe_proxy_cost), "이체건수": tobe_txn_count},
])
cost_compare.to_csv(r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\compare_transfer_cost.csv", index=False, encoding="utf-8-sig")

# ============================================================
# [4] 저장조건별 배치 적합도 검증
# ============================================================
print("\n" + "=" * 90)
print("[4] 저장조건별 배치 적합도 검증")
print("=" * 90)

violations = []
for c in CENTERS:
    for storage in ["실온", "냉동", "냉장"]:
        if storage in STORAGE_SUPPORT[c]:
            continue
        bad_rows = tobe[(tobe["center_id"] == c) & (tobe["storage_type"] == storage) & (tobe["TO_BE_stock_kg"] > 1e-6)]
        if len(bad_rows) > 0:
            violations.append((c, storage, len(bad_rows), bad_rows["TO_BE_stock_kg"].sum()))

if violations:
    print("위반 발견:")
    for v in violations:
        print(f"  센터{v[0]} x {v[1]}: {v[2]}건, {v[3]:,.1f}kg")
else:
    print("위반 0건 - 모든 TO-BE 배치가 센터별 저장조건 지원범위 내에 있음 (설계상 해당 변수를 아예 생성하지 않았으므로 구조적으로 보장됨)")

# 참고: 몇 개 조합이 저장조건 제약으로 아예 원천 배제됐는지
n_excluded = sum(1 for _, r in df.iterrows() for c in CENTERS if r["상품 정보_저장조건"] not in STORAGE_SUPPORT[c])
print(f"(참고) 저장조건 부적합으로 원천 배제된 SKU-센터 조합: {n_excluded}건 / 5,000건")

# ============================================================
# [5] Before/After/개선율 요약 카드
# ============================================================
print("\n" + "=" * 90)
print("[5] Before / After / 개선율 요약")
print("=" * 90)

summary = pd.DataFrame([
    {"지표": "센터간 재고회전일수 격차(최대-최소)", "AS-IS": f"{gap_asis:.2f}일", "TO-BE": f"{gap_tobe:.2f}일",
     "개선율": f"{(1-gap_tobe/gap_asis)*100:.1f}%"},
    {"지표": "1센터-3센터 재고회전일수 격차", "AS-IS": f"{c1_c3_gap_asis:.2f}일", "TO-BE": f"{c1_c3_gap_tobe:.2f}일",
     "개선율": f"{(1-c1_c3_gap_tobe/c1_c3_gap_asis)*100:.1f}%"},
    {"지표": "악성재고 조합 재고량(128건 합)", "AS-IS": f"{asis_bad_kg:,.0f}kg", "TO-BE": f"{tobe_bad_kg:,.0f}kg",
     "개선율": f"{(1-tobe_bad_kg/asis_bad_kg)*100:.1f}%"},
    {"지표": "이체비용 [단위 다름 - 주3 참조]", "AS-IS": f"{asis_proxy_cost:,.0f}원/월(반복)", "TO-BE": f"{tobe_proxy_cost:,.0f}원(1회성)",
     "개선율": f"전환비용=월비용의 {payback_pct:.1f}%"},
    {"지표": "이체건수 [단위 다름 - 주3 참조]", "AS-IS": f"{asis_txn_count}건/월(반복)", "TO-BE": f"{tobe_txn_count}건(1회성)",
     "개선율": f"전환건수=월건수의 {tobe_txn_count/asis_txn_count*100:.1f}%"},
    {"지표": "저장조건 부적합 배치 위반", "AS-IS": "N/A(제약 미적용)", "TO-BE": f"{len(violations)}건",
     "개선율": "위반 0건 달성" if not violations else "위반 존재"},
])
print("\n주3) 이체비용/건수의 AS-IS는 '월간 반복 발생'하는 운영비이고 TO-BE는 AS-IS->TO-BE로 전환하는")
print("     '1회성' 비용이라 서로 성격이 다르다 - 두 지표는 직접 뺄셈/절감률로 해석하지 말 것")
print(summary.to_string(index=False))
summary.to_csv(r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\compare_summary_cards.csv", index=False, encoding="utf-8-sig")

print("\n" + "=" * 90)
print("[DONE]")
print("=" * 90)

# -*- coding: utf-8 -*-
"""
거점 간 다품종 재고 최적화 - 사전과제
CJ프레시웨이 '25년6월이체출고실적' 분석 스크립트

구성:
  [1] 데이터 로드 & 2행 병합헤더 평탄화 & 이체량 NaN 처리
  [2] 구조/기초통계 요약
  [3] SKU x 센터 패널(재고/출고/회전율) 생성 & 이상치 점검
  [4] 가상 변수 정의: 센터 Capa / 배송권역 / 이체비용 / 안전재고
  [5] 최적화 입력용 SKU x 센터 최종 스키마 조립 & CSV 저장
"""
import numpy as np
import pandas as pd

PATH = r"cj프레시웨이.xlsx"
SHEET = "25년6월이체출고실적"

# ============================================================
# [1] 로드 & 헤더 평탄화 & NaN 처리
# ============================================================
df = pd.read_excel(PATH, sheet_name=SHEET, header=[0, 1])
df.columns = [f"{str(top).strip()}_{str(sub).strip()}" for top, sub in df.columns]

transfer_cols = [c for c in df.columns if "이체량" in c]
df[transfer_cols] = df[transfer_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

STOCK_COLS = {i: f"각 센터별 재고 보유 수량(최소단위 기준)_{i}센터" for i in range(1, 6)}
OUT_COLS = {i: f"각 센터별 월 출고량(kg)_{i}센터" for i in range(1, 6)}
UNIT_W = df["상품 정보_최소단위 중량"]
LEAD = df["상품 정보_발주 리드타임"]


def inbound_cols(c):
    return [col for col in df.columns if col.startswith(f"{c}센터 필요에 따른 이체량(kg)_")]


def outbound_cols(c):
    return [f"{n}센터 필요에 따른 이체량(kg)_{c}센터" for n in range(1, 6) if n != c]


# ============================================================
# [3] SKU x 센터 패널
# ============================================================
panel_records = []
for c in range(1, 6):
    stock_c = df[STOCK_COLS[c]]
    stock_kg = stock_c * UNIT_W
    out_c = df[OUT_COLS[c]]
    inbound = df[inbound_cols(c)].sum(axis=1)
    outbound = df[outbound_cols(c)].sum(axis=1)

    panel_records.append(pd.DataFrame({
        "상품코드": df["상품 정보_상품코드"],
        "센터": c,
        "재고량_최소단위": stock_c,
        "재고량_kg": stock_kg,
        "월출고량_kg": out_c,
        "이체유입_kg": inbound,
        "이체유출_kg": outbound,
        "회전율_kg(출고kg/재고kg)": (out_c / stock_kg.replace(0, np.nan)).round(3),
    }))
panel = pd.concat(panel_records, ignore_index=True)

# ============================================================
# [4] 가상 변수: Capa / 권역 / 이체비용 / 안전재고
# ============================================================
center_summary = []
for i in range(1, 6):
    stock_kg = (df[STOCK_COLS[i]] * UNIT_W).sum()
    out_kg = df[OUT_COLS[i]].sum()
    cv = df[OUT_COLS[i]].std() / df[OUT_COLS[i]].mean()
    center_summary.append({"센터": i, "재고합_kg": stock_kg, "출고합_kg": out_kg, "출고CV": cv})
cs = pd.DataFrame(center_summary)

BASE_MARGIN, CV_COEF = 0.20, 0.15
cs["여유율"] = (BASE_MARGIN + CV_COEF * cs["출고CV"]).round(3)
cs["Capa_kg"] = (cs["재고합_kg"] * (1 + cs["여유율"])).round(1)

REGION_COORDS = {
    "수도권": (127.00, 37.50), "충청권": (127.40, 36.30), "호남권": (126.90, 35.20),
    "영남권": (128.80, 35.30), "강원권": (127.70, 37.80),
}
rank_by_outbound = cs.sort_values("출고합_kg", ascending=False)["센터"].tolist()
CENTER_REGION = dict(zip(rank_by_outbound, ["수도권", "영남권", "충청권", "호남권", "강원권"]))


def haversine(c1, c2):
    lon1, lat1, lon2, lat2 = *c1, *c2
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


BASE_RATE, RATE_PER_KM = 500, 0.8  # 원/kg 고정비, 원/kg/km
transfer_cost = {}
for i in range(1, 6):
    for j in range(1, 6):
        if i == j:
            continue
        d = haversine(REGION_COORDS[CENTER_REGION[i]], REGION_COORDS[CENTER_REGION[j]])
        transfer_cost[(i, j)] = round(BASE_RATE + d * RATE_PER_KM, 1)

SAFETY_FACTOR = 0.5  # 1개월 스냅샷이라 수요표준편차 대신 사용하는 근사 계수

# ============================================================
# [5] 최종 SKU x 센터 스키마 조립
# ============================================================
schema_records = []
for c in range(1, 6):
    stock_c = df[STOCK_COLS[c]]
    stock_kg = stock_c * UNIT_W
    out_c = df[OUT_COLS[c]]
    daily_out = out_c / 30.0
    safety_kg = daily_out * LEAD * SAFETY_FACTOR
    capa_kg = cs.loc[cs["센터"] == c, "Capa_kg"].values[0]

    schema_records.append(pd.DataFrame({
        "sku_id": df["상품 정보_상품코드"],
        "sku_name": df["상품 정보_상품명"],
        "storage_type": df["상품 정보_저장조건"],
        "category": df["상품 정보_상품범주"],
        "unit_weight_kg": UNIT_W,
        "lead_time_day": LEAD,
        "center_id": c,
        "region": CENTER_REGION[c],
        "stock_qty_unit": stock_c,
        "stock_kg": stock_kg,
        "monthly_outbound_kg": out_c,
        "daily_avg_outbound_kg": daily_out.round(3),
        "transfer_in_kg": df[inbound_cols(c)].sum(axis=1),
        "transfer_out_kg": df[outbound_cols(c)].sum(axis=1),
        "turnover_kg": (out_c / stock_kg.replace(0, np.nan)).round(3),
        "safety_stock_kg": safety_kg.round(2),
        "center_capa_kg": capa_kg,
    }))
schema_df = pd.concat(schema_records, ignore_index=True)

center_stock_actual = schema_df.groupby("center_id")["stock_kg"].sum()
schema_df["capa_utilization_pct"] = schema_df["center_id"].map(
    lambda c: round(center_stock_actual[c] / cs.loc[cs["센터"] == c, "Capa_kg"].values[0] * 100, 2)
)

if __name__ == "__main__":
    print("df shape:", df.shape)
    print("panel(SKU x 센터) shape:", panel.shape)
    print("\n센터별 요약:\n", cs)
    print("\n센터-권역 매핑:", CENTER_REGION)
    print("\n최종 스키마 shape:", schema_df.shape)
    panel.to_csv("sku_center_panel.csv", index=False, encoding="utf-8-sig")
    schema_df.to_csv("sku_center_optimization_schema.csv", index=False, encoding="utf-8-sig")
    print("\nsaved: sku_center_panel.csv, sku_center_optimization_schema.csv")

# -*- coding: utf-8 -*-
"""
거점 간 다품종 재고 최적화 - TO-BE 배치 최적화
- LP(PuLP/CBC) 정식 모델 + 규칙기반 휴리스틱 비교
"""
import time
import numpy as np
import pandas as pd
import pulp

import scm_inventory_analysis as base

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

df = base.df
panel = base.panel.copy()
cs = base.cs.copy()
CENTER_REGION = base.CENTER_REGION
transfer_cost = base.transfer_cost  # dict (i,j) -> 원/kg
UNIT_W = base.UNIT_W
LEAD = base.LEAD

CENTERS = [1, 2, 3, 4, 5]
CAPA = dict(zip(cs["센터"], cs["Capa_kg"]))

# ============================================================
# [0] 가상 변수: 센터별 저장조건 지원
#     AS-IS 데이터 확인 결과 3센터는 보유재고 56개 SKU 전부(112,003kg, 100%)가 냉동이고
#     실온/냉장 재고는 0 -> 냉동 전용 특화 거점으로 가정(실온/냉장은 재고 없이 JIT 이체로만 커버 중)
# ============================================================
STORAGE_SUPPORT = {
    1: {"실온", "냉동", "냉장"},
    2: {"실온", "냉동", "냉장"},
    3: {"냉동"},                  # 냉동 전용 거점 가정 (AS-IS 재고 100%가 냉동)
    4: {"실온", "냉동", "냉장"},
    5: {"실온", "냉동", "냉장"},
}
storage_map = df.set_index("상품 정보_상품코드")["상품 정보_저장조건"]

# ============================================================
# [1] 악성재고 태깅 (2단계와 동일 로직 재현)
# ============================================================
valid = panel["재고량_kg"] > 0
threshold20 = panel.loc[valid, "회전율_kg(출고kg/재고kg)"].quantile(0.20)
panel["회전율_하위20pct"] = valid & (panel["회전율_kg(출고kg/재고kg)"] <= threshold20)
panel["악성재고"] = panel["회전율_하위20pct"] & (panel["이체유입_kg"] > 0)
badstock_set = set(zip(panel.loc[panel["악성재고"], "상품코드"], panel.loc[panel["악성재고"], "센터"]))
print(f"악성재고 조합: {len(badstock_set)}건")

# ============================================================
# [2] 파라미터 준비: SKU 단위 dict
# ============================================================
sku_ids = df["상품 정보_상품코드"].tolist()
lead_map = dict(zip(df["상품 정보_상품코드"], df["상품 정보_발주 리드타임"]))
storage_type_map = dict(zip(df["상품 정보_상품코드"], df["상품 정보_저장조건"]))

stock0 = {}   # (sku, center) -> AS-IS 재고 kg
out0 = {}     # (sku, center) -> AS-IS 월출고 kg
safety = {}   # (sku, center) -> 안전재고 kg
for c in CENTERS:
    stock_c = (df[base.STOCK_COLS[c]] * UNIT_W)
    out_c = df[base.OUT_COLS[c]]
    daily_out = out_c / 30.0
    safety_kg = daily_out * LEAD * base.SAFETY_FACTOR
    for sku, s, o, sf in zip(sku_ids, stock_c, out_c, safety_kg):
        stock0[(sku, c)] = float(s)
        out0[(sku, c)] = float(o)
        safety[(sku, c)] = float(sf)

# 센터별 이체 평균단가(원/kg) : 다른 4개 센터 -> j 로 들어오는 평균 비용
avgcost_to = {j: np.mean([transfer_cost[(k, j)] for k in CENTERS if k != j]) for j in CENTERS}
print("\n센터별 평균 이체입고 단가(원/kg):", {k: round(v, 1) for k, v in avgcost_to.items()})

# 총재고(SKU) - 개별 센터 kg 합으로 재계산(합계 컬럼 불일치 이슈 회피)
total_stock = {sku: sum(stock0[(sku, c)] for c in CENTERS) for sku in sku_ids}

# 센터 적합성(E_i) / 수요존재(D_i) 집합
eligible = {}   # sku -> set(centers)
demand_ok = {}  # sku -> set(centers)  (수요 있고 & 저장조건 적합)
demand_risk = {}  # sku -> set(centers) (수요는 있는데 저장조건 부적합 - 리스크 플래그)
for sku in sku_ids:
    st = storage_type_map[sku]
    elig = {c for c in CENTERS if st in STORAGE_SUPPORT[c]}
    eligible[sku] = elig
    d_all = {c for c in CENTERS if out0[(sku, c)] > 0}
    demand_ok[sku] = d_all & elig
    demand_risk[sku] = d_all - elig

n_zero_total = sum(1 for sku in sku_ids if total_stock[sku] == 0)
n_risk = sum(len(v) for v in demand_risk.values())
print(f"총재고 0인 SKU: {n_zero_total}건 (안전재고 하드제약 제외 대상)")
print(f"수요는 있는데 저장조건 부적합(리스크) 조합: {n_risk}건 -> 이 조합은 로컬재고 없이 100% JIT 이체로만 커버")

# 안전재고 총합이 실제 총재고를 초과하는 SKU는 비례 축소(하드제약 유지, 실행가능하도록 스케일다운)
n_scaled = 0
for sku in sku_ids:
    need = sum(safety[(sku, c)] for c in demand_ok[sku])
    have = total_stock[sku]
    if need > have and need > 0:
        scale = (have * 0.98) / need  # 부동소수점 경계 여유 2%
        for c in demand_ok[sku]:
            safety[(sku, c)] *= scale
        n_scaled += 1
print(f"안전재고 비례축소 적용 SKU: {n_scaled}건 (필요안전재고합 > 보유총재고 -> 총재고 98% 한도로 비례배분)")

PENALTY_RATE_LT = 50     # 원/kg/day - 리드타임 가중 부족분 페널티
PENALTY_RATE_BAD = 300   # 원/kg - 악성재고 잔존 페널티
SAFETY_BUFFER_TARGET = 1.5  # 소프트 목표재고 = 안전재고 x 1.5

# ============================================================
# [3] LP 모델 (PuLP)
# ============================================================
print("\n" + "=" * 80)
print("[3] PuLP LP 모델 빌드 & 풀이")
print("=" * 80)

t0 = time.time()
prob = pulp.LpProblem("TOBE_inventory_allocation", pulp.LpMinimize)

x, inc, shortfall = {}, {}, {}
for sku in sku_ids:
    for c in eligible[sku]:
        x[(sku, c)] = pulp.LpVariable(f"x_{sku}_{c}", lowBound=0)
        inc[(sku, c)] = pulp.LpVariable(f"inc_{sku}_{c}", lowBound=0)
    for c in demand_ok[sku]:
        shortfall[(sku, c)] = pulp.LpVariable(f"short_{sku}_{c}", lowBound=0)

print(f"변수 개수: x={len(x)}, inc={len(inc)}, shortfall={len(shortfall)}  (총 {len(x)+len(inc)+len(shortfall)})")

# 목적함수
transfer_term = pulp.lpSum(inc[(sku, c)] * avgcost_to[c] for (sku, c) in inc)
leadtime_term = pulp.lpSum(shortfall[(sku, c)] * lead_map[sku] * PENALTY_RATE_LT for (sku, c) in shortfall)
badstock_term = pulp.lpSum(x[(sku, c)] * PENALTY_RATE_BAD for (sku, c) in x if (sku, c) in badstock_set)
prob += transfer_term + leadtime_term + badstock_term

# 제약 1: SKU 총재고 보존 (재배치만 수행, 총량 불변)
for sku in sku_ids:
    if total_stock[sku] == 0:
        continue
    prob += pulp.lpSum(x[(sku, c)] for c in eligible[sku]) == total_stock[sku], f"conserve_{sku}"

# 제약 2: 저장조건 부적합 센터는 변수 자체를 안 만들었으므로 자동 충족

# 제약 3: 안전재고 하한 (수요 있고 저장조건 적합한 곳만)
for sku in sku_ids:
    if total_stock[sku] == 0:
        continue
    for c in demand_ok[sku]:
        prob += x[(sku, c)] >= safety[(sku, c)], f"safety_{sku}_{c}"
        prob += shortfall[(sku, c)] >= safety[(sku, c)] * SAFETY_BUFFER_TARGET - x[(sku, c)], f"short_{sku}_{c}"

# 제약 4: 센터 Capa
for c in CENTERS:
    prob += pulp.lpSum(x[(sku, c)] for sku in sku_ids if c in eligible[sku]) <= CAPA[c], f"capa_{c}"

# 이체증가량 선형화
for (sku, c) in x:
    prob += inc[(sku, c)] >= x[(sku, c)] - stock0[(sku, c)], f"inc_def_{sku}_{c}"

build_time = time.time() - t0
t1 = time.time()
solver = pulp.PULP_CBC_CMD(msg=False)
prob.solve(solver)
solve_time = time.time() - t1

print(f"모델 빌드 시간: {build_time:.2f}s, 풀이 시간: {solve_time:.2f}s")
print("상태:", pulp.LpStatus[prob.status])
lp_obj = pulp.value(prob.objective)
print(f"목적함수 값(LP): {lp_obj:,.0f} 원")
print(f"  - 이관비용: {pulp.value(transfer_term):,.0f} 원")
print(f"  - 리드타임 페널티: {pulp.value(leadtime_term):,.0f} 원")
print(f"  - 악성재고 페널티: {pulp.value(badstock_term):,.0f} 원")

# TO-BE 결과 취합
tobe_records = []
for sku in sku_ids:
    for c in eligible[sku]:
        v = x[(sku, c)].value() or 0.0
        tobe_records.append({
            "sku_id": sku, "center_id": c,
            "storage_type": storage_type_map[sku],
            "AS_IS_stock_kg": round(stock0[(sku, c)], 2),
            "TO_BE_stock_kg": round(v, 2),
            "변화_kg": round(v - stock0[(sku, c)], 2),
            "안전재고_kg": round(safety[(sku, c)], 2),
            "악성재고_AS_IS": (sku, c) in badstock_set,
        })
tobe_df = pd.DataFrame(tobe_records)
print("\nTO-BE 배치 샘플(변화량 큰 상위 10건):")
print(tobe_df.reindex(tobe_df["변화_kg"].abs().sort_values(ascending=False).index).head(10).to_string(index=False))

out_csv = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\tobe_allocation_LP.csv"
tobe_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
print("saved:", out_csv)

# 3센터는 냉동만 취급 가능 - 실온/냉장 변수 자체가 없으므로 위반 불가(설계상 자동 충족)
c3_frozen_tobe = tobe_df.loc[(tobe_df["center_id"] == 3) & (tobe_df["storage_type"] == "냉동"), "TO_BE_stock_kg"].sum()
c3_frozen_asis = sum(stock0[(sku, 3)] for sku in sku_ids if storage_type_map[sku] == "냉동")
print(f"\n3센터 냉동 재고: AS-IS {c3_frozen_asis:,.0f}kg -> TO-BE {c3_frozen_tobe:,.0f}kg")

print("\n" + "=" * 80)
print("[DONE - LP]")
print("=" * 80)

# ============================================================
# [4] 규칙기반 휴리스틱: 회전율 낮은 순 + Capa 여유 있는 센터로 우선 재배치
# ============================================================
print("\n" + "=" * 80)
print("[4] 휴리스틱 빌드 & 실행")
print("=" * 80)

t2 = time.time()

turnover_map = dict(zip(zip(panel["상품코드"], panel["센터"]), panel["회전율_kg(출고kg/재고kg)"]))
badstock_sorted = sorted(badstock_set, key=lambda p: turnover_map.get(p, 0))  # 회전율 낮은 순(worst first)

heur_stock = dict(stock0)  # 휴리스틱 결과 (AS-IS 복사본에서 시작)
running_total = {c: sum(stock0[(sku, c)] for sku in sku_ids) for c in CENTERS}

n_moved_pairs, kg_moved_total, n_blocked = 0, 0.0, 0
for (sku, source) in badstock_sorted:
    movable = max(heur_stock[(sku, source)] - safety.get((sku, source), 0.0), 0.0)
    if movable <= 0:
        continue
    dests = sorted(eligible[sku] - {source}, key=lambda c: CAPA[c] - running_total[c], reverse=True)  # Capa 여유 큰 순
    for dest in dests:
        if movable <= 0:
            break
        headroom = CAPA[dest] - running_total[dest]
        if headroom <= 0:
            continue
        moved = min(movable, headroom)
        heur_stock[(sku, source)] -= moved
        heur_stock[(sku, dest)] = heur_stock.get((sku, dest), 0.0) + moved
        running_total[source] -= moved
        running_total[dest] += moved
        movable -= moved
        kg_moved_total += moved
        n_moved_pairs += 1
    if movable > 1e-6:
        n_blocked += 1  # 네트워크 전체 Capa 여유 부족으로 일부 미이동

heuristic_time = time.time() - t2
print(f"휴리스틱 실행시간: {heuristic_time:.3f}s")
print(f"이동 발생 건수: {n_moved_pairs}건, 총 이동량: {kg_moved_total:,.1f} kg, Capa부족으로 미이동 잔존: {n_blocked}건")

# 휴리스틱 결과를 동일한 목적함수 기준으로 평가(= LP와 공정 비교용)
def eval_objective(stock_dict):
    transfer_c, lt_c, bad_c = 0.0, 0.0, 0.0
    for sku in sku_ids:
        for c in eligible[sku]:
            v = stock_dict.get((sku, c), 0.0)
            inc_v = max(v - stock0[(sku, c)], 0.0)
            transfer_c += inc_v * avgcost_to[c]
            if (sku, c) in badstock_set:
                bad_c += v * PENALTY_RATE_BAD
        for c in demand_ok[sku]:
            v = stock_dict.get((sku, c), 0.0)
            target = safety[(sku, c)] * SAFETY_BUFFER_TARGET
            short = max(target - v, 0.0)
            lt_c += short * lead_map[sku] * PENALTY_RATE_LT
    return transfer_c, lt_c, bad_c

h_transfer, h_lt, h_bad = eval_objective(heur_stock)
h_obj = h_transfer + h_lt + h_bad
print(f"휴리스틱 목적함수 값(LP와 동일 기준): {h_obj:,.0f} 원")
print(f"  - 이관비용: {h_transfer:,.0f} 원 / 리드타임 페널티: {h_lt:,.0f} 원 / 악성재고 페널티: {h_bad:,.0f} 원")

# 제약 위반 여부 점검
viol_capa = {c: running_total[c] - CAPA[c] for c in CENTERS if running_total[c] - CAPA[c] > 1e-6}
viol_safety = 0
for sku in sku_ids:
    for c in demand_ok[sku]:
        if heur_stock.get((sku, c), 0.0) < safety[(sku, c)] - 1e-6:
            viol_safety += 1
print(f"Capa 위반 센터: {viol_capa if viol_capa else '없음'}")
print(f"안전재고 미달 조합: {viol_safety}건")

# ============================================================
# [5] LP vs 휴리스틱 비교
# ============================================================
print("\n" + "=" * 80)
print("[5] LP vs 휴리스틱 비교")
print("=" * 80)
compare = pd.DataFrame([
    {"방식": "LP(PuLP/CBC)", "빌드+풀이시간(s)": round(build_time + solve_time, 3),
     "목적함수(원)": round(lp_obj), "이관비용": round(pulp.value(transfer_term)),
     "리드타임페널티": round(pulp.value(leadtime_term)), "악성재고페널티": round(pulp.value(badstock_term)),
     "변수 스코프": "전체 4,410개 (i,j) 조합 재최적화"},
    {"방식": "휴리스틱(그리디)", "빌드+풀이시간(s)": round(heuristic_time, 3),
     "목적함수(원)": round(h_obj), "이관비용": round(h_transfer),
     "리드타임페널티": round(h_lt), "악성재고페널티": round(h_bad),
     "변수 스코프": f"악성재고 128건만 대상 이동"},
])
print(compare.to_string(index=False))
gap_pct = (h_obj - lp_obj) / lp_obj * 100
print(f"\n휴리스틱은 LP 대비 목적함수 {gap_pct:+.1f}% (이 값이 클수록 LP 대비 비효율) / "
      f"풀이속도는 LP가 이미 1초 미만이라 이 규모에서는 속도 이점이 크지 않음")

heur_records = []
for sku in sku_ids:
    for c in eligible[sku]:
        v = heur_stock.get((sku, c), 0.0)
        heur_records.append({
            "sku_id": sku, "center_id": c, "storage_type": storage_type_map[sku],
            "AS_IS_stock_kg": round(stock0[(sku, c)], 2), "TO_BE_stock_kg_heuristic": round(v, 2),
            "변화_kg": round(v - stock0[(sku, c)], 2),
        })
heur_df = pd.DataFrame(heur_records)
heur_csv = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\tobe_allocation_heuristic.csv"
heur_df.to_csv(heur_csv, index=False, encoding="utf-8-sig")
print("saved:", heur_csv)

compare_csv = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\lp_vs_heuristic_comparison.csv"
compare.to_csv(compare_csv, index=False, encoding="utf-8-sig")
print("saved:", compare_csv)

print("\n" + "=" * 80)
print("[ALL DONE]")
print("=" * 80)

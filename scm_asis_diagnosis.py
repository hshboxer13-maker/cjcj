# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"c:\Users\hshbo\OneDrive\바탕 화면\코딩")
import numpy as np
import pandas as pd
import scm_inventory_analysis as base

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

df = base.df
panel = base.panel.copy()
cs = base.cs.copy()
CENTER_REGION = base.CENTER_REGION

# ============================================================
# [1] 센터별 적재율 진단
# ============================================================
print("=" * 80)
print("[1] 센터별 적재율 진단")
print("=" * 80)

cd = cs.copy()
cd["적재율_Capa기준_pct"] = (cd["재고합_kg"] / cd["Capa_kg"] * 100).round(2)
cd["재고비중_pct"] = (cd["재고합_kg"] / cd["재고합_kg"].sum() * 100).round(2)
cd["출고비중_pct"] = (cd["출고합_kg"] / cd["출고합_kg"].sum() * 100).round(2)
cd["비중격차(재고-출고)_pct"] = (cd["재고비중_pct"] - cd["출고비중_pct"]).round(2)
cd["재고회전일수"] = (cd["재고합_kg"] / (cd["출고합_kg"] / 30)).round(2)

mean_days = cd["재고회전일수"].mean()
def status(d):
    if d > mean_days * 1.3:
        return "과적재 후보(회전 느림)"
    if d < mean_days * 0.5:
        return "저활용/재고부족 후보(회전 매우 빠름=이체 의존)"
    return "정상범위"
cd["진단"] = cd["재고회전일수"].apply(status)

print(cd[["센터", "재고합_kg", "Capa_kg", "적재율_Capa기준_pct"]].to_string(index=False))
print(f"\n>>> Capa기준 적재율은 {cd['적재율_Capa기준_pct'].min():.1f}~{cd['적재율_Capa기준_pct'].max():.1f}%로 "
      f"센터간 거의 동일 (구조적 원인: Capa 자체를 '현재재고 x (1+여유율)'로 정의했기 때문에 "
      f"어느 센터든 적재율이 1/(1+여유율) 근방으로 수렴함. 즉 이 정의로는 1센터-3센터의 "
      f"극단적 규모차이가 적재율(%)에 드러나지 않음 - Capa 정의 자체의 한계.")

print("\n>>> 대안 진단: 재고비중 vs 출고비중 격차 / 재고회전일수(=재고를 며칠치 갖고 있는가)")
print(cd[["센터", "재고비중_pct", "출고비중_pct", "비중격차(재고-출고)_pct", "재고회전일수", "진단"]].to_string(index=False))
print(f"\n네트워크 평균 재고회전일수: {mean_days:.2f}일")
print(">>> 여기서 1센터(재고 93.6만kg) vs 3센터(재고 11.2만kg)의 극단적 차이가 실제로 드러나는 지점:")
print("    - 3센터는 재고비중 4.4%인데 출고비중은 16.3%를 담당 -> 재고 대비 훨씬 많은 물량을 처리")
print("      (재고회전일수 2.47일 = 거의 무재고로 운영, 이체에 절대적으로 의존)")
print("    - 5센터는 재고비중 18.2%, 출고비중 10.6% -> 자기 처리량 대비 재고를 과다 보유")
print("      (재고회전일수 15.51일로 네트워크 평균 9.39일의 1.65배)")

cd.to_csv(r"C:\Users\hshbo\AppData\Local\Temp\claude\c--Users-hshbo-OneDrive---------\fadaea6e-571b-4ccb-bba7-56b78e8d192a\scratchpad\center_diagnosis.csv",
          index=False, encoding="utf-8-sig")

# ============================================================
# [2] 악성재고 태깅
# ============================================================
print("\n" + "=" * 80)
print("[2] 악성재고 태깅 (회전율 하위 20% & 이체유입 발생)")
print("=" * 80)

valid = panel["재고량_kg"] > 0
threshold20 = panel.loc[valid, "회전율_kg(출고kg/재고kg)"].quantile(0.20)
print(f"회전율 계산 가능 모집단(재고>0): {valid.sum()}건 / 전체 {len(panel)}건")
print(f"회전율 하위 20% 임계값 (turnover_kg <= {threshold20:.4f})")

panel["회전율_하위20pct"] = valid & (panel["회전율_kg(출고kg/재고kg)"] <= threshold20)
panel["악성재고"] = panel["회전율_하위20pct"] & (panel["이체유입_kg"] > 0)

n_low20 = panel["회전율_하위20pct"].sum()
n_bad = panel["악성재고"].sum()
print(f"회전율 하위 20% 조합: {n_low20}건")
print(f"그 중 이체유입까지 발생한 '악성재고' 조합: {n_bad}건 ({n_bad/len(panel)*100:.2f}% of 전체 SKU-센터)")
print(f"악성재고 조합의 이체유입 kg 합계: {panel.loc[panel['악성재고'], '이체유입_kg'].sum():,.1f} kg")

print("\n악성재고 샘플 10건:")
sample = panel[panel["악성재고"]].merge(
    df[["상품 정보_상품코드", "상품 정보_상품명", "상품 정보_저장조건", "상품 정보_상품범주"]],
    left_on="상품코드", right_on="상품 정보_상품코드", how="left"
).sort_values("이체유입_kg", ascending=False)
print(sample[["상품코드", "상품 정보_상품명", "센터", "재고량_kg", "월출고량_kg",
              "회전율_kg(출고kg/재고kg)", "이체유입_kg"]].head(10).to_string(index=False))

panel.to_csv(r"C:\Users\hshbo\AppData\Local\Temp\claude\c--Users-hshbo-OneDrive---------\fadaea6e-571b-4ccb-bba7-56b78e8d192a\scratchpad\panel_tagged.csv",
             index=False, encoding="utf-8-sig")

# ============================================================
# [3] 센터별 요약 테이블
# ============================================================
print("\n" + "=" * 80)
print("[3] 센터별 이체/악성재고 요약")
print("=" * 80)

center_bad = panel.groupby("센터").agg(
    이체유입합_kg=("이체유입_kg", "sum"),
    이체유출합_kg=("이체유출_kg", "sum"),
    이체수신SKU건수=("이체유입_kg", lambda s: (s > 0).sum()),
    악성재고건수=("악성재고", "sum"),
    전체SKU수=("상품코드", "count"),
).reset_index()
center_bad["악성재고비중_전체SKU대비_pct"] = (center_bad["악성재고건수"] / center_bad["전체SKU수"] * 100).round(2)
center_bad["악성재고비중_이체수신SKU대비_pct"] = (center_bad["악성재고건수"] / center_bad["이체수신SKU건수"] * 100).round(2)
center_bad["권역"] = center_bad["센터"].map(CENTER_REGION)

print(center_bad.to_string(index=False))
center_bad.to_csv(r"C:\Users\hshbo\AppData\Local\Temp\claude\c--Users-hshbo-OneDrive---------\fadaea6e-571b-4ccb-bba7-56b78e8d192a\scratchpad\center_bad_summary.csv",
                   index=False, encoding="utf-8-sig")

# ============================================================
# [4] 저장조건별 이체 패턴
# ============================================================
print("\n" + "=" * 80)
print("[4] 저장조건별 이체 패턴")
print("=" * 80)

storage_map = df.set_index("상품 정보_상품코드")["상품 정보_저장조건"]
panel["저장조건"] = panel["상품코드"].map(storage_map)

storage_diag = panel.groupby("저장조건").agg(
    SKU센터조합수=("상품코드", "count"),
    평균재고_kg=("재고량_kg", "mean"),
    평균월출고_kg=("월출고량_kg", "mean"),
    평균회전율=("회전율_kg(출고kg/재고kg)", "mean"),
    이체유입합_kg=("이체유입_kg", "sum"),
    이체유출합_kg=("이체유출_kg", "sum"),
    이체수신비율_pct=("이체유입_kg", lambda s: (s > 0).mean() * 100),
    악성재고건수=("악성재고", "sum"),
).reset_index()
storage_diag["악성재고비율_pct"] = (storage_diag["악성재고건수"] / storage_diag["SKU센터조합수"] * 100).round(2)
storage_diag["평균회전율"] = storage_diag["평균회전율"].round(3)
storage_diag["이체유입_SKU조합당_kg"] = (storage_diag["이체유입합_kg"] / storage_diag["SKU센터조합수"]).round(2)

print(storage_diag.to_string(index=False))

# 저장조건 x 센터 이체유입 교차표도 참고용으로
cross = panel.pivot_table(index="저장조건", columns="센터", values="이체유입_kg", aggfunc="sum").round(1)
print("\n저장조건 x 센터 이체유입 합계(kg) 교차표:\n", cross)

storage_diag.to_csv(r"C:\Users\hshbo\AppData\Local\Temp\claude\c--Users-hshbo-OneDrive---------\fadaea6e-571b-4ccb-bba7-56b78e8d192a\scratchpad\storage_diagnosis.csv",
                     index=False, encoding="utf-8-sig")

print("\n" + "=" * 80)
print("[DONE]")
print("=" * 80)

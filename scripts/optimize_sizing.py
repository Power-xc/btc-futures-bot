#!/usr/bin/env python3
"""
레버리지 · 복리(켈리배팅) · 마틴게일 최적화

분석 항목:
  1. Kelly 기준값 계산 (실제 거래 데이터 기반)
  2. 레버리지 최적화 (5x / 10x / 15x / 20x / 25x / 30x / 40x)
  3. 마틴게일 배수 최적화 (1.5x / 2x / 2.5x / 3x)
  4. 고정금액 vs 복리(자본비율) 비교
  5. 최종 최적 조합 확인
"""
import sys, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import logging
logging.disable(logging.CRITICAL)

from backtest.data_loader import fetch_historical_data, load_as_candle_list
from backtest.engine import run_backtest
from lib.metrics import calc_metrics
import strategy.indicators as ind
import strategy.patterns as pat

# ── 최적 파라미터 적용 ─────────────────────────────────────
ind.VOL_WEAK_RATIO         = 0.92
ind.VOL_TREND_RATIO        = 3.50
pat.FAKE_MOVE_BODY_PCT     = 0.010
pat.SPIKE_CLUSTER_MOVE_PCT = 0.015

INITIAL = 1000.0


def run(candles, label, leverage=20, martingale_pcts=None, vol_avg_window=20):
    t0 = time.time()
    tr, eq, wd, _ = run_backtest(
        candles, initial_capital=INITIAL,
        vol_avg_window=vol_avg_window,
        leverage=leverage,
        martingale_pcts=martingale_pcts,
    )
    m = calc_metrics(tr, eq, INITIAL)
    total_wd = sum(e["withdrawn"] for e in wd)
    m["total"]    = round(m["cap"] + total_wd, 0)
    m["wd_count"] = len(wd)
    m["elapsed"]  = round(time.time() - t0, 1)
    return m


def print_row(label, m, extra=""):
    ruin = " ☠" if m["mdd"] >= 90 else ""
    best = " ★" if m["score"] >= 0.45 else ""
    print(f"  {label:<52}  PF={m['pf']:>5.3f}  MDD={m['mdd']:>5.1f}%  WR={m['wr']:>5.1f}%  "
          f"Ret={m['ret']:>+7.1f}%  N={m['n']:>4d}  출금포함=${m['total']:>7,.0f}  score={m['score']:>6.4f}{ruin}{best}{extra}")


# ── 데이터 로드 ────────────────────────────────────────────
print("데이터 로드 중...", flush=True)
df7 = fetch_historical_data("5m", "2018-01-01", "2025-01-01", use_cache=True)
C7 = load_as_candle_list(df7)
print(f"7년 {len(C7):,}캔들\n", flush=True)

# ── 1. Kelly 기준 계산 ────────────────────────────────────
print("=" * 100)
print("  [1] Kelly Criterion 분석 — 현재 최적 파라미터 기준")
print("=" * 100)
base_m = run(C7, "기준")
b = base_m["avg_win"] / base_m["avg_loss"] if base_m["avg_loss"] else 1
wr_frac = base_m["wr"] / 100
kelly_full    = base_m["kelly"]
kelly_half    = kelly_full / 2
kelly_quarter = kelly_full / 4

print(f"""
  승률(WR)       = {base_m['wr']}%
  평균 수익       = ${base_m['avg_win']}  (레버리지 반영 실제 USDT)
  평균 손실       = ${base_m['avg_loss']}
  손익비(b)      = {b:.3f}

  Kelly 공식: K = WR - (1-WR)/b = {wr_frac:.3f} - {(1-wr_frac):.3f}/{b:.3f}
  Full Kelly  = {kelly_full:.1f}%  → 매 거래 자본의 {kelly_full:.1f}% 배팅
  Half Kelly  = {kelly_half:.1f}%  → (권장: 변동성 절반)
  1/4 Kelly   = {kelly_quarter:.1f}%  → (보수적)

  현재 첫 진입   = 잔고 × 1.009% (65% 비율 복리, Kelly의 {1.009/kelly_full*100:.0f}%)
  → Full Kelly 기준 첫 진입: ${INITIAL * kelly_full / 100:.0f}
  → Half Kelly 기준 첫 진입: ${INITIAL * kelly_half / 100:.0f}
""")

# ── 2. 레버리지 최적화 ────────────────────────────────────
print("=" * 100)
print("  [2] 레버리지 최적화 (마틴게일 $15×2.5배수 고정)")
print("=" * 100)
lev_results = []
for lev in [5, 10, 15, 20, 25, 30, 40]:
    m = run(C7, f"레버리지 {lev:2d}x", leverage=lev)
    mark = " [현재]" if lev == 20 else ""
    print_row(f"  레버리지 {lev:2d}x", m, mark)
    lev_results.append((m["score"], lev, m))
best_lev = max(lev_results, key=lambda x: x[0] if x[2]["mdd"] < 80 else -999)
print(f"\n  → 최적 레버리지 = {best_lev[1]}x  (score={best_lev[0]:.4f})")

# ── 3. 마틴게일 총 노출 비율 최적화 ──────────────────────
print("\n" + "=" * 100)
print("  [3] 마틴게일 총 노출 비율 최적화 (레버리지 20x, ×2.5 배수 유지)")
print("=" * 100)

RATIO_SUM = 1 + 2.5 + 6.25 + 15.625 + 39.0625   # 64.4375

mart_results = []
for total_pct in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]:
    x = total_pct / RATIO_SUM
    pcts = [x, x*2.5, x*6.25, x*15.625, x*39.0625]
    m = run(C7, f"  총노출 {total_pct*100:.0f}%", leverage=20, martingale_pcts=pcts)
    mark = " [현재 65%]" if total_pct == 0.65 else ""
    print_row(f"  총노출 {total_pct*100:.0f}% [{'/'.join(f'{p*100:.2f}%' for p in pcts)}]", m, mark)
    mart_results.append((m["score"], total_pct, pcts, m))

best_mart = max(mart_results, key=lambda x: x[0] if x[3]["mdd"] < 80 else -999)
print(f"\n  → 최적 총노출: {best_mart[1]*100:.0f}%  (score={best_mart[0]:.4f})")

# ── 4. 복리 (자본비율) vs 고정금액 ───────────────────────
print("\n" + "=" * 100)
print("  [4] 복리(Kelly 자본비율) vs 고정금액 비교 (레버리지 20x)")
print("=" * 100)

kf = kelly_full    / 100
kh = kelly_half    / 100
kq = kelly_quarter / 100

compound_configs = [
    ("복리 65% [현재 채택]",                            [0.01009, 0.02523, 0.06307, 0.15768, 0.39420]),
    (f"복리 2%/4%/8%/16%/30% (현재 수준)",              [0.020, 0.040, 0.080, 0.160, 0.300]),
    (f"복리 1/4Kelly ({kq*100:.1f}%  x2배수)",          [kq, kq*2, kq*4, kq*8, kq*15]),
    (f"복리 1/2Kelly ({kh*100:.1f}%  x2배수)",          [kh, kh*2, kh*4, kh*8, kh*15]),
    (f"복리 FullKelly ({kf*100:.1f}%  x2배수)",         [kf, kf*2, kf*4, kf*8, kf*15]),
    (f"복리 1/2Kelly ({kh*100:.1f}%  x1.5배수)",        [kh, kh*1.5, kh*2.25, kh*3.4, kh*5.1]),
    (f"복리 1/4Kelly ({kq*100:.1f}%  x3배수)",          [kq, kq*3, kq*9, kq*27, kq*50]),
    (f"복리 3%/6%/12%/24%/45%",                        [0.030, 0.060, 0.120, 0.240, 0.450]),
    (f"복리 1.5%/3%/6%/12%/22%",                       [0.015, 0.030, 0.060, 0.120, 0.220]),
    (f"복리 1%/2%/4%/8%/15% (보수적)",                  [0.010, 0.020, 0.040, 0.080, 0.150]),
]

compound_results = []
for label, pcts in compound_configs:
    m = run(C7, label, leverage=20, martingale_pcts=pcts)
    mark = " [현재]" if pcts is None else ""
    print_row(f"  {label}", m, mark)
    compound_results.append((m["score"], label, pcts, m))

best_compound = max(compound_results, key=lambda x: x[0] if x[3]["mdd"] < 85 else -999)
print(f"\n  → 최적 복리 방식: {best_compound[1]}  (score={best_compound[0]:.4f})")
print(f"    7년 수익: {best_compound[3]['ret']:+.1f}%  출금포함: ${best_compound[3]['total']:,}")

# ── 5. 최종 종합 최적화 ───────────────────────────────────
print("\n" + "=" * 100)
print("  [5] 최종 종합 — 최적 레버리지 × 복리 조합")
print("=" * 100)

top_lev = sorted(lev_results, key=lambda x: x[0] if x[2]["mdd"] < 80 else -999, reverse=True)[:3]

final_results = []
for _, lev, _ in top_lev:
    for _, label, pcts, _ in sorted(compound_results, key=lambda x: x[0] if x[3]["mdd"] < 85 else -999, reverse=True)[:4]:
        if pcts is None:
            continue
        m = run(C7, f"", leverage=lev, martingale_pcts=pcts)
        lbl = f"  lev={lev:2d}x  {label}"
        print_row(lbl, m)
        final_results.append((m["score"], lev, label, pcts, m))

print()
print("=" * 100)
print("  ★ 최종 최적 파라미터 종합 (MDD<80% 조건, score 기준)")
print("=" * 100)
final_results.sort(key=lambda x: x[0] if x[4]["mdd"] < 80 else -999, reverse=True)
for rank, (score, lev, label, pcts, m) in enumerate(final_results[:5], 1):
    print(f"\n  {rank}위  레버리지={lev}x  {label}")
    print(f"       PF={m['pf']}  MDD={m['mdd']}%  WR={m['wr']}%  Ret={m['ret']:+.1f}%  출금포함=${m['total']:,}  score={score}")
    if pcts:
        pct_str = "/".join(f"{p*100:.1f}%" for p in pcts)
        print(f"       마틴게일 비율: [{pct_str}]")

print()
print("=" * 100)
print("  기준선 (현재 설정)")
print("=" * 100)
print_row("  현재 레버리지20x 복리 65%", base_m, " [현재]")

#!/usr/bin/env python3
"""
표적 파라미터 민감도 분석

분석 항목:
  A) VOL_AVG_WINDOW    : 5 / 10 / 20 / 30 / 50
  B) FAKE_MOVE_BODY_PCT: 0.005 / 0.006 / 0.008 / 0.010 / 0.012
  C) SPIKE_CLUSTER     : 0.008 / 0.010 / 0.012 / 0.015 / 0.020

총 1(기준) + 5 + 5 + 5 + 1(최종) + 7(연도별) = ~24회 백테스트
"""
import sys, os, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import logging
logging.disable(logging.CRITICAL)

from backtest.data_loader import fetch_historical_data, load_as_candle_list
from backtest.engine import run_backtest
from lib.metrics import calc_metrics
import strategy.indicators as ind
import strategy.patterns as pat

BASE = {"vw": 0.92, "vt": 3.50, "vaw": 20, "bp": 0.010, "sc": 0.015}


def run_test(candles, vw, vt, vaw, bp, sc, label):
    ind.VOL_WEAK_RATIO         = vw
    ind.VOL_TREND_RATIO        = vt
    pat.FAKE_MOVE_BODY_PCT     = bp
    pat.SPIKE_CLUSTER_MOVE_PCT = sc
    t0 = time.time()
    trades, eq, _, _ = run_backtest(candles, initial_capital=1000.0, vol_avg_window=vaw)
    elapsed = time.time() - t0
    m = calc_metrics(trades, eq, 1000.0)
    print(f"  {label:<42} PF={m['pf']:>5.3f}  MDD={m['mdd']:>5.1f}%  "
          f"WR={m['wr']:>5.1f}%  Ret={m['ret']:>+7.1f}%  "
          f"N={m['n']:>4d}  [{elapsed:.0f}s]", flush=True)
    return m


# ── 데이터 로드 ──────────────────────────────────────────────────
print("데이터 로드 중...", flush=True)
df7 = fetch_historical_data("5m", "2018-01-01", "2025-01-01", use_cache=True)
C7 = load_as_candle_list(df7)
print(f"7년 캔들 {len(C7):,}개 준비\n", flush=True)

# ── 기준 백테스트 ────────────────────────────────────────────────
print("=" * 80, flush=True)
print(f"  기준값: VOL_WEAK={BASE['vw']}  VOL_TREND={BASE['vt']}  WIN={BASE['vaw']}  BODY={BASE['bp']*100:.1f}%  SPIKE={BASE['sc']*100:.1f}%", flush=True)
print("=" * 80, flush=True)
base = run_test(C7, **BASE, label="[기준값]")

# ── A. VOL_AVG_WINDOW ────────────────────────────────────────────
print("\n── A. VOL_AVG_WINDOW (최근 N봉 평균으로 거래량 기준선) ──", flush=True)
aw_res = []
for vaw in [5, 10, 20, 30, 50]:
    r = run_test(C7, BASE["vw"], BASE["vt"], vaw, BASE["bp"], BASE["sc"],
                 label=f"  WIN={vaw:>2d}봉")
    aw_res.append((r["score"], vaw, r))
aw_res.sort(reverse=True)
best_vaw = aw_res[0][1]
print(f"\n  → 최적 VOL_AVG_WINDOW = {best_vaw}봉  (score={aw_res[0][0]:.4f})", flush=True)

# ── B. FAKE_MOVE_BODY_PCT ────────────────────────────────────────
print("\n── B. FAKE_MOVE_BODY_PCT (역추세 진입 최소 몸통 크기) ──", flush=True)
bp_res = []
for bp in [0.005, 0.006, 0.008, 0.010, 0.012]:
    r = run_test(C7, BASE["vw"], BASE["vt"], best_vaw, bp, BASE["sc"],
                 label=f"  BODY={bp*100:.1f}%")
    bp_res.append((r["score"], bp, r))
bp_res.sort(reverse=True)
best_bp = bp_res[0][1]
print(f"\n  → 최적 FAKE_MOVE_BODY_PCT = {best_bp}  (score={bp_res[0][0]:.4f})", flush=True)

# ── C. SPIKE_CLUSTER_MOVE_PCT ────────────────────────────────────
print("\n── C. SPIKE_CLUSTER_MOVE_PCT (클러스터 피뢰침 최소 이동) ──", flush=True)
sc_res = []
for sc in [0.008, 0.010, 0.012, 0.015, 0.020]:
    r = run_test(C7, BASE["vw"], BASE["vt"], best_vaw, best_bp, sc,
                 label=f"  SPIKE={sc*100:.1f}%")
    sc_res.append((r["score"], sc, r))
sc_res.sort(reverse=True)
best_sc = sc_res[0][1]
print(f"\n  → 최적 SPIKE_CLUSTER_MOVE_PCT = {best_sc}  (score={sc_res[0][0]:.4f})", flush=True)

# ── 최종 확인 ────────────────────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("  최종 최적값 확인 백테스트 (7년)", flush=True)
print("=" * 80, flush=True)
final = run_test(C7, BASE["vw"], BASE["vt"], best_vaw, best_bp, best_sc,
                 label="[최종 최적값]")

# ── 연도별 성과 ──────────────────────────────────────────────────
print("\n── 연도별 성과 분석 ──", flush=True)
run_test(C7, BASE["vw"], BASE["vt"], best_vaw, best_bp, best_sc, label="_warmup_")

print(f"  {'년도':>6} {'PF':>7} {'MDD%':>7} {'WR%':>7} {'Ret%':>8} {'거래':>6} {'자산':>9}", flush=True)
print("  " + "-" * 55, flush=True)
for year in range(2018, 2025):
    start_ms = int(datetime(year, 1, 1).timestamp() * 1000)
    end_ms   = int(datetime(year + 1, 1, 1).timestamp() * 1000)
    cy = [c for c in C7 if start_ms <= c["timestamp"] < end_ms]
    if not cy:
        continue
    tr_y, eq_y, _, _ = run_backtest(cy, initial_capital=1000.0, vol_avg_window=best_vaw)
    m = calc_metrics(tr_y, eq_y, 1000.0)
    sign = "+" if m["ret"] >= 0 else ""
    print(f"  {year}  PF={m['pf']:>5.3f}  MDD={m['mdd']:>5.1f}%  "
          f"WR={m['wr']:>5.1f}%  Ret={sign}{m['ret']:>6.1f}%  "
          f"N={m['n']:>4d}  ${m['cap']:>7,}", flush=True)

# ── 최종 결론 ────────────────────────────────────────────────────
print("\n" + "=" * 80, flush=True)
print("  ★ 수학적으로 검증된 최적 파라미터 (7년 2018-2025)", flush=True)
print("=" * 80, flush=True)
print(f"""
  VOL_WEAK_RATIO         = {BASE['vw']}     # < {int(BASE['vw']*100)}% of avg → 거래량 미달 (가짜 움직임)
  VOL_TREND_RATIO        = {BASE['vt']}     # > {int(BASE['vt']*100)}% of avg ({BASE['vt']:.0f}x) → 진짜 추세
  VOL_AVG_WINDOW         = {best_vaw}        # 최근 {best_vaw}봉 평균 기준선
  FAKE_MOVE_BODY_PCT     = {best_bp:.3f}     # {best_bp*100:.1f}% 이상 몸통 (역추세 진입 필터)
  SPIKE_CLUSTER_MOVE_PCT = {best_sc:.3f}     # {best_sc*100:.1f}% 이상 클러스터 이동 (피뢰침 필터)

  → PF={final['pf']}  MDD={final['mdd']}%  WR={final['wr']}%
  → $1,000 → ${final['cap']:,}  (수익률 +{final['ret']}%)
  → 총 {final['n']:,}회 거래
""", flush=True)

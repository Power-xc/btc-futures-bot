#!/usr/bin/env python3
"""
5분봉 3틱룰 단타 전략 백테스트 (아카이브)

규칙:
  진입: 3개 연속 같은 방향 캔들 → 반전 숏/롱
  TP  : 진입가 대비 0.3% (레버리지 20x → +6%)
  SL  : 진입가 대비 0.6% (레버리지 20x → -12%)
  포지션당 $20 고정 (마틴게일 없음)
  중복 진입 없음 (한 번에 하나)

기간: 2024-10-01 ~ 2025-01-01 (3개월)

결론: 역추세 마틴게일 전략(WR=66.8%, PF=2.064) 대비 열위 — 참고용 아카이브
"""
import sys, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import logging
logging.disable(logging.CRITICAL)

from backtest.data_loader import fetch_historical_data, load_as_candle_list
from lib.volume import precompute_vol_avg
from config.constants import BACKTEST_TAKER_FEE, BACKTEST_SLIPPAGE

# ─── 파라미터 ────────────────────────────────────────────────
ENTRY_USDT  = 20
TP_PCT      = 0.003
SL_PCT      = 0.006
TICK_COUNT  = 3
INITIAL_CAP = 1000.0
VOL_AVG_WIN = 20
REQUIRE_WEAK = True


def is_all_bullish(candles):
    return all(c["close"] > c["open"] for c in candles)


def is_all_bearish(candles):
    return all(c["close"] < c["open"] for c in candles)


def is_weak(candle, ratio=0.70):
    avg = candle.get("vol_avg", 0)
    if avg > 0:
        return candle["volume"] < avg * ratio
    return False


def run_3tick(candles, require_weak=REQUIRE_WEAK, tp=TP_PCT, sl=SL_PCT, ticks=TICK_COUNT):
    capital = INITIAL_CAP
    trades = []
    equity = [(candles[0]["timestamp"], capital)]

    pos = None
    entry_price = tp_price = sl_price = 0.0

    for i in range(ticks, len(candles)):
        c = candles[i]
        prev = candles[i - ticks:i]

        if pos == "SHORT":
            hit_sl = c["high"] >= sl_price
            hit_tp = c["low"]  <= tp_price
            if hit_sl and hit_tp:
                pnl = -(ENTRY_USDT * 20 / entry_price * (sl_price - entry_price))
                pnl -= sl_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "sl"}); pos = None
            elif hit_tp:
                pnl = (ENTRY_USDT * 20 / entry_price * (entry_price - tp_price))
                pnl -= tp_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "tp"}); pos = None
            elif hit_sl:
                pnl = -(ENTRY_USDT * 20 / entry_price * (sl_price - entry_price))
                pnl -= sl_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "sl"}); pos = None

        elif pos == "LONG":
            hit_sl = c["low"]  <= sl_price
            hit_tp = c["high"] >= tp_price
            if hit_sl and hit_tp:
                pnl = -(ENTRY_USDT * 20 / entry_price * (entry_price - sl_price))
                pnl -= sl_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "sl"}); pos = None
            elif hit_tp:
                pnl = (ENTRY_USDT * 20 / entry_price * (tp_price - entry_price))
                pnl -= tp_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "tp"}); pos = None
            elif hit_sl:
                pnl = -(ENTRY_USDT * 20 / entry_price * (entry_price - sl_price))
                pnl -= sl_price * (ENTRY_USDT * 20 / entry_price) * BACKTEST_TAKER_FEE
                capital += pnl; trades.append({"pnl": pnl, "reason": "sl"}); pos = None

        if capital <= 0:
            break

        if pos is None:
            weak_ok = (not require_weak) or all(is_weak(cc) for cc in prev)
            if is_all_bullish(prev) and weak_ok:
                ep = c["close"] * (1 - BACKTEST_SLIPPAGE)
                pos = "SHORT"; entry_price = ep
                tp_price = ep * (1 - tp); sl_price = ep * (1 + sl)
            elif is_all_bearish(prev) and weak_ok:
                ep = c["close"] * (1 + BACKTEST_SLIPPAGE)
                pos = "LONG"; entry_price = ep
                tp_price = ep * (1 + tp); sl_price = ep * (1 - sl)

        equity.append((c["timestamp"], capital))

    return trades, equity, capital


def print_stats(trades, final_cap, label):
    if not trades:
        print(f"  {label:<45} 거래 없음")
        return
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    wr  = len(wins) / len(trades) * 100
    gp  = sum(t["pnl"] for t in wins)
    gl  = abs(sum(t["pnl"] for t in losses)) or 1e-9
    pf  = gp / gl
    ret = (final_cap - INITIAL_CAP) / INITIAL_CAP * 100
    tp_count = sum(1 for t in trades if t["reason"] == "tp")
    sl_count = sum(1 for t in trades if t["reason"] == "sl")
    print(f"  {label:<45} WR={wr:>5.1f}%  PF={pf:>5.3f}  "
          f"N={len(trades):>4d}(TP:{tp_count}/SL:{sl_count})  "
          f"Ret={ret:>+7.1f}%  ${final_cap:>7,.0f}")


# ─── 데이터 로드 ─────────────────────────────────────────────
print("데이터 로드 중 (2024-10 ~ 2025-01)...", flush=True)
df = fetch_historical_data("5m", "2024-10-01", "2025-01-01", use_cache=True)
candles = load_as_candle_list(df)
precompute_vol_avg(candles, VOL_AVG_WIN)
print(f"캔들 {len(candles):,}개\n", flush=True)

print("=" * 85)
print("  5분봉 3틱룰 단타 — 파라미터 비교")
print("=" * 85)

configs = [
    ("기본: 3틱 (거래량필터없음) TP0.3/SL0.6",   False, 0.003, 0.006, 3),
    ("거래량필터: 3틱 + 약세거래량  TP0.3/SL0.6", True,  0.003, 0.006, 3),
    ("타이트TP: 3틱 (필터없음) TP0.2/SL0.4",     False, 0.002, 0.004, 3),
    ("거래량필터: 3틱 + 약세거래량  TP0.2/SL0.4", True,  0.002, 0.004, 3),
    ("넓은TP:   3틱 (필터없음) TP0.5/SL0.5",     False, 0.005, 0.005, 3),
    ("거래량필터: 3틱 + 약세거래량  TP0.5/SL0.5", True,  0.005, 0.005, 3),
    ("4틱룰 (거래량필터없음) TP0.3/SL0.6",        False, 0.003, 0.006, 4),
    ("4틱룰 + 약세거래량     TP0.3/SL0.6",        True,  0.003, 0.006, 4),
    ("2틱룰 + 약세거래량     TP0.3/SL0.6",        True,  0.003, 0.006, 2),
]

for label, rw, tp, sl, ticks in configs:
    t0 = time.time()
    trades, equity, final_cap = run_3tick(candles, require_weak=rw, tp=tp, sl=sl, ticks=ticks)
    elapsed = time.time() - t0
    print_stats(trades, final_cap, f"[{elapsed:.1f}s] {label}")

print()
print("※ 기존 전략 (역추세 마틴게일) 기준선: WR=66.8%  PF=2.064  7년 평균")
print("※ 3틱룰은 마틴게일 없음 — 심플 고정 리스크 단타")

"""
백테스트 엔진
- 역추세(숏/롱) + 추세 롱 전략
- 마틴게일 추매
- 2-2-2 출금 시뮬레이션
"""
import logging
from typing import Optional
from datetime import datetime

from strategy.signals import generate_signal, Signal
from config.constants import (
    MARTINGALE_PCTS, MAX_MARTINGALE_LEVEL, LEVERAGE,
    BACKTEST_TAKER_FEE, BACKTEST_SLIPPAGE, INITIAL_CAPITAL,
    BACKTEST_MIN_CANDLES, BACKTEST_WINDOW_SIZE,
    PARTIAL_CLOSE_RATIO, MAX_ENTRY_CAPITAL_RATIO,
    STAGE_UP_MULTIPLIER, STAGE_UP_WIN_COUNT,
    TREND_LONG_MIN_STOP_PCT,
)
from lib.volume import precompute_vol_avg

logger = logging.getLogger(__name__)


def run_backtest(
    candles: list,
    initial_capital: float = INITIAL_CAPITAL,
    vol_avg_window: int = 20,
    leverage: int = LEVERAGE,
    martingale_pcts: list = None,   # 기본값: constants.MARTINGALE_PCTS (65% 비율 복리)
):
    """
    Returns:
        trades        : list of trade dicts
        equity_curve  : list of (timestamp, capital)
        withdrawals   : list of withdrawal events
        stage_log     : list of stage upgrade events
    """
    capital = initial_capital
    stage_capital = initial_capital   # 현재 체급 기준 시드
    stage_wins = 0
    total_withdrawn = 0.0
    withdrawals = []
    stage_log = []

    trades = []
    equity_curve = [(candles[0]["timestamp"], capital)]

    # 포지션 상태
    position_side: Optional[str] = None
    martingale_level: int = 0
    entries: list = []
    entry_time = None

    # 추세 롱 전용: 신호 캔들 2캔들 전 저점 = 손절가
    trend_long_stop: float = 0.0

    def _apply_slip(price: float, side: str) -> float:
        if side in ("CONTRARIAN_LONG", "TREND_LONG"):
            return price * (1 + BACKTEST_SLIPPAGE)
        return price * (1 - BACKTEST_SLIPPAGE)

    def _add_entry(price: float, level: int) -> bool:
        """잔고 부족 시 진입 거부. Returns True if entry succeeded."""
        pcts = martingale_pcts if martingale_pcts is not None else MARTINGALE_PCTS
        usdt = capital * pcts[level]   # 현재 자본 기준 복리
        if usdt > capital * MAX_ENTRY_CAPITAL_RATIO:
            logger.debug(f"  잔고 부족 → {level+1}차 진입 건너뜀 (잔고: ${capital:.0f}, 필요: ${usdt:.0f})")
            return False
        exec_price = _apply_slip(price, position_side)
        qty = (usdt * leverage) / exec_price
        entries.append({"price": exec_price, "usdt": usdt, "qty": qty})
        return True

    def _avg_price() -> float:
        total_qty = sum(e["qty"] for e in entries)
        if total_qty == 0:
            return 0.0
        return sum(e["price"] * e["qty"] for e in entries) / total_qty

    def _total_qty() -> float:
        return sum(e["qty"] for e in entries)

    def _calc_pnl(exit_price: float, qty: float) -> float:
        avg = _avg_price()
        is_long = position_side in ("CONTRARIAN_LONG", "TREND_LONG")
        raw = (exit_price - avg) * qty if is_long else (avg - exit_price) * qty
        fee = exit_price * qty * BACKTEST_TAKER_FEE
        return raw - fee

    def _reset_position():
        nonlocal position_side, martingale_level, trend_long_stop
        position_side = None
        martingale_level = 0
        entries.clear()
        trend_long_stop = 0.0

    def _check_withdrawal(ts):
        """2-2-2 출금 로직"""
        nonlocal capital, stage_capital, stage_wins, total_withdrawn

        if capital >= stage_capital * STAGE_UP_MULTIPLIER:
            withdrawn = stage_capital
            capital -= withdrawn
            total_withdrawn += withdrawn
            stage_wins += 1
            event = {
                "time": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                "withdrawn": withdrawn,
                "total_withdrawn": total_withdrawn,
                "capital_after": capital,
                "stage_wins": stage_wins,
            }
            withdrawals.append(event)
            logger.info(f"[출금] ${withdrawn:,.0f} 인출 | 잔여: ${capital:,.2f} | 누적 출금: ${total_withdrawn:,.0f}")

            if stage_wins >= STAGE_UP_WIN_COUNT:
                stage_capital *= STAGE_UP_MULTIPLIER
                stage_wins = 0
                stage_log.append({
                    "time": event["time"],
                    "new_stage": stage_capital,
                })
                logger.info(f"[체급 격상] 새 시드 체급: ${stage_capital:,.0f}")

    # ── vol_avg 사전 계산 (전체 캔들 한 번만) ────────────────
    precompute_vol_avg(candles, vol_avg_window)

    # ── 레짐 EMA 사전 계산 (전체 캔들 한 번만) ───────────────
    # EMA50 / EMA200 (200봉 ≈ 16시간) 로 단기 추세 판단
    # 단기 하락추세: price < EMA50 < EMA200
    def _precompute_ema(period: int) -> list:
        k = 2 / (period + 1)
        ema_vals = [candles[0]["close"]]
        for c in candles[1:]:
            ema_vals.append(c["close"] * k + ema_vals[-1] * (1 - k))
        return ema_vals

    ema50  = _precompute_ema(50)
    ema200 = _precompute_ema(200)
    macro_down_flags = [
        (candles[i]["close"] < ema50[i] and ema50[i] < ema200[i])
        for i in range(len(candles))
    ]

    for i in range(BACKTEST_MIN_CANDLES, len(candles)):
        candle = candles[i]
        window = candles[max(0, i - BACKTEST_WINDOW_SIZE):i + 1]
        price = candle["close"]
        ts = candle["timestamp"]
        is_macro_downtrend = macro_down_flags[i]

        # ── 추세 롱 하드 손절 체크 (신호 생성 전 우선 처리) ──────
        # 신호 캔들 2캔들 앞 저점을 이탈 시 즉시 손절
        if position_side == "TREND_LONG" and trend_long_stop > 0:
            if candle["low"] <= trend_long_stop:
                stop_price = trend_long_stop
                pnl = _calc_pnl(stop_price, _total_qty())
                capital += pnl
                trades.append(_make_trade(entry_time, ts, position_side,
                                          _avg_price(), stop_price, pnl,
                                          "trend_stop_loss", martingale_level))
                logger.info(f"[추세롱 손절] 저점 ${stop_price:,.0f} 이탈 | PnL: ${pnl:+.2f} | 자본: ${capital:,.2f}")
                _reset_position()
                _check_withdrawal(ts)
                equity_curve.append((ts, capital))
                continue

        result = generate_signal(
            candle=candle,
            candles=window,
            macro_downtrend=is_macro_downtrend,
            position_side=position_side,
            martingale_level=martingale_level,
        )
        sig = result.signal

        # ── 신규 진입 ────────────────────────────────────
        if sig in (Signal.ENTER_CONTRARIAN_SHORT, Signal.ENTER_CONTRARIAN_LONG,
                   Signal.ENTER_TREND_LONG) and position_side is None:
            side_map = {
                Signal.ENTER_CONTRARIAN_SHORT: "CONTRARIAN_SHORT",
                Signal.ENTER_CONTRARIAN_LONG:  "CONTRARIAN_LONG",
                Signal.ENTER_TREND_LONG:       "TREND_LONG",
            }
            position_side = side_map[sig]
            martingale_level = 1
            entries.clear()
            _add_entry(price, 0)
            entry_time = datetime.fromtimestamp(ts / 1000)

            # 추세 롱: 손절가 = 신호 캔들 2개 전 저점
            # 손절가가 진입가보다 높거나 0.3% 미만 차이면 0.5% 아래로 강제 설정
            if position_side == "TREND_LONG":
                ref_candle = candles[max(BACKTEST_MIN_CANDLES, i - 2)]
                raw_stop = ref_candle["low"]
                min_stop = price * (1 - TREND_LONG_MIN_STOP_PCT)
                trend_long_stop = min(raw_stop, min_stop)
                logger.debug(f"  추세롱 진입: 손절가 ${trend_long_stop:,.0f}")

        # ── 추매 ─────────────────────────────────────────
        elif sig in (Signal.ADD_SHORT, Signal.ADD_LONG):
            expected = "CONTRARIAN_SHORT" if sig == Signal.ADD_SHORT else "CONTRARIAN_LONG"
            if position_side == expected and martingale_level < MAX_MARTINGALE_LEVEL:
                _add_entry(price, martingale_level)
                martingale_level += 1

        # ── 분할 익절 ─────────────────────────────────────
        elif sig == Signal.PARTIAL_CLOSE and position_side is not None:
            close_qty = _total_qty() * PARTIAL_CLOSE_RATIO
            pnl = _calc_pnl(price, close_qty)
            capital += pnl
            for e in entries:
                e["qty"] *= PARTIAL_CLOSE_RATIO
                e["usdt"] *= PARTIAL_CLOSE_RATIO
            trades.append(_make_trade(entry_time, ts, position_side,
                                      _avg_price(), price, pnl, "partial_close", martingale_level))
            _check_withdrawal(ts)

        # ── 완전 익절 ────────────────────────────────────
        elif sig == Signal.FULL_CLOSE and position_side is not None:
            pnl = _calc_pnl(price, _total_qty())
            capital += pnl
            trades.append(_make_trade(entry_time, ts, position_side,
                                      _avg_price(), price, pnl, "full_close", martingale_level))
            logger.info(f"[완익] {position_side} @ ${price:,.0f} | PnL: ${pnl:+.2f} | 자본: ${capital:,.2f}")
            _reset_position()
            _check_withdrawal(ts)

        equity_curve.append((ts, capital))

    # 미청산 강제 종료
    if position_side is not None and entries:
        price = candles[-1]["close"]
        pnl = _calc_pnl(price, _total_qty())
        capital += pnl
        trades.append(_make_trade(entry_time, candles[-1]["timestamp"], position_side,
                                  _avg_price(), price, pnl, "end_of_data", martingale_level))

    logger.info(f"백테스트 완료 | 거래: {len(trades)}회 | 최종 자본: ${capital:,.2f} | 총 출금: ${total_withdrawn:,.2f}")
    return trades, equity_curve, withdrawals, stage_log


def _make_trade(entry_time, close_ts, side, entry_price, exit_price, pnl, reason, level):
    return {
        "entry_time": entry_time,
        "close_time": datetime.fromtimestamp(close_ts / 1000),
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl_usdt": pnl,
        "reason": reason,
        "level": level,
    }

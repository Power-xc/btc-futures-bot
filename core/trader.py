"""
실시간 트레이딩 루프

동작 방식:
  1. 매 5분봉 마감 직후 (+3초 여유) 캔들 로드
  2. vol_avg / EMA 계산
  3. generate_signal() 호출
  4. 시그널에 따라 주문 실행
  5. 포지션 상태 저장

폴링 방식 채택 (WebSocket 대비 단순, 5분봉에 충분)
"""
import logging
import time
from datetime import datetime, timezone

import ccxt

import notifications.telegram as tg
from exchange.client import (
    create_client, check_connection,
    set_leverage, set_margin_mode,
    fetch_closed_candles, get_position,
    get_usdt_balance,
)
from exchange.order import enter_long, enter_short, close_partial, close_full
from core.state import PositionState, load_state, save_state, clear_state
from strategy.signals import generate_signal, Signal
from lib.volume import precompute_vol_avg
from config.constants import (
    LEVERAGE, BACKTEST_MIN_CANDLES, BACKTEST_WINDOW_SIZE,
    MARTINGALE_AMOUNTS, MAX_MARTINGALE_LEVEL,
    TREND_LONG_MIN_STOP_PCT,
)

logger = logging.getLogger(__name__)

CANDLE_LIMIT      = 300     # 로드할 캔들 수 (EMA200 + 여유분)
TIMEFRAME         = "5m"
POLL_INTERVAL_SEC = 10      # 캔들 마감 체크 주기 (초)
CANDLE_SEC        = 300     # 5분봉 = 300초


def _candle_close_time_sec(now_sec: int) -> int:
    """현재 시각 기준 다음 캔들 마감 시각 (초) 반환"""
    return (now_sec // CANDLE_SEC + 1) * CANDLE_SEC


def _wait_for_next_candle():
    """다음 5분봉 마감 후 3초까지 슬립"""
    now = int(time.time())
    next_close = _candle_close_time_sec(now)
    wait = next_close - now + 3   # +3초 여유 (캔들 확정 대기)
    logger.info(f"[대기] 다음 캔들 마감까지 {wait}초")
    time.sleep(wait)


def _precompute_ema(candles: list, period: int) -> list:
    k = 2 / (period + 1)
    ema = [candles[0]["close"]]
    for c in candles[1:]:
        ema.append(c["close"] * k + ema[-1] * (1 - k))
    return ema


def _is_macro_downtrend(candles: list, idx: int,
                        ema50: list, ema200: list) -> bool:
    return (candles[idx]["close"] < ema50[idx]
            and ema50[idx] < ema200[idx])


def _log_status(state: PositionState, balance: float, price: float):
    if state.is_open():
        pnl_est = 0.0
        if state.entries:
            is_long = state.position_side in ("CONTRARIAN_LONG", "TREND_LONG")
            pnl_est = (price - state.avg_price()) * state.total_qty()
            if not is_long:
                pnl_est = -pnl_est
        logger.info(
            f"[상태] {state.position_side} lv={state.martingale_level} | "
            f"평균가: ${state.avg_price():,.0f} | 미실현 PnL: ${pnl_est:+.2f} | "
            f"잔고: ${balance:.2f}"
        )
    else:
        logger.info(f"[상태] 미보유 | 잔고: ${balance:.2f} | 현재가: ${price:,.0f}")


def _handle_signal(exchange: ccxt.binanceusdm,
                   sig: Signal,
                   reason: str,
                   state: PositionState,
                   candle: dict,
                   candles: list,
                   idx: int) -> bool:
    """
    시그널 처리 → 주문 실행 + 상태 업데이트

    Returns True if state was changed
    """
    price = candle["close"]
    changed = False

    balance = get_usdt_balance(exchange)

    # ── 신규 진입 ────────────────────────────────────────────
    if sig == Signal.ENTER_CONTRARIAN_SHORT and not state.is_open():
        order = enter_short(exchange, price, level=0)
        if order:
            qty = float(order.get("filled", 0) or MARTINGALE_AMOUNTS[0] / price)
            state.position_side    = "CONTRARIAN_SHORT"
            state.martingale_level = 1
            state.entries.clear()
            state.add_entry(price, MARTINGALE_AMOUNTS[0], qty)
            changed = True
            logger.info(f"[시그널] {reason}")
            tg.notify_enter("CONTRARIAN_SHORT", 1, price, MARTINGALE_AMOUNTS[0], balance)

    elif sig == Signal.ENTER_CONTRARIAN_LONG and not state.is_open():
        order = enter_long(exchange, price, level=0)
        if order:
            qty = float(order.get("filled", 0) or MARTINGALE_AMOUNTS[0] / price)
            state.position_side    = "CONTRARIAN_LONG"
            state.martingale_level = 1
            state.entries.clear()
            state.add_entry(price, MARTINGALE_AMOUNTS[0], qty)
            changed = True
            logger.info(f"[시그널] {reason}")
            tg.notify_enter("CONTRARIAN_LONG", 1, price, MARTINGALE_AMOUNTS[0], balance)

    elif sig == Signal.ENTER_TREND_LONG and not state.is_open():
        order = enter_long(exchange, price, level=0)
        if order:
            qty = float(order.get("filled", 0) or MARTINGALE_AMOUNTS[0] / price)
            state.position_side    = "TREND_LONG"
            state.martingale_level = 1
            state.entries.clear()
            state.add_entry(price, MARTINGALE_AMOUNTS[0], qty)
            ref = candles[max(0, idx - 2)]
            min_stop = price * (1 - TREND_LONG_MIN_STOP_PCT)
            state.trend_long_stop = min(ref["low"], min_stop)
            changed = True
            logger.info(f"[시그널] {reason} | 손절: ${state.trend_long_stop:,.0f}")
            tg.notify_enter("TREND_LONG", 1, price, MARTINGALE_AMOUNTS[0], balance)

    # ── 추매 ─────────────────────────────────────────────────
    elif sig == Signal.ADD_SHORT and state.position_side == "CONTRARIAN_SHORT":
        if state.martingale_level < MAX_MARTINGALE_LEVEL:
            lv = state.martingale_level
            order = enter_short(exchange, price, level=lv)
            if order:
                qty = float(order.get("filled", 0) or MARTINGALE_AMOUNTS[lv] / price)
                state.add_entry(price, MARTINGALE_AMOUNTS[lv], qty)
                state.martingale_level += 1
                changed = True
                tg.notify_enter("CONTRARIAN_SHORT", lv + 1, price, MARTINGALE_AMOUNTS[lv], balance)

    elif sig == Signal.ADD_LONG and state.position_side == "CONTRARIAN_LONG":
        if state.martingale_level < MAX_MARTINGALE_LEVEL:
            lv = state.martingale_level
            order = enter_long(exchange, price, level=lv)
            if order:
                qty = float(order.get("filled", 0) or MARTINGALE_AMOUNTS[lv] / price)
                state.add_entry(price, MARTINGALE_AMOUNTS[lv], qty)
                state.martingale_level += 1
                changed = True
                tg.notify_enter("CONTRARIAN_LONG", lv + 1, price, MARTINGALE_AMOUNTS[lv], balance)

    # ── 분할 익절 ─────────────────────────────────────────────
    elif sig == Signal.PARTIAL_CLOSE and state.is_open():
        from config.constants import PARTIAL_CLOSE_RATIO
        avg = state.avg_price()
        order = close_partial(exchange, price, state.position_side)
        if order:
            for e in state.entries:
                e["qty"]  *= (1 - PARTIAL_CLOSE_RATIO)
                e["usdt"] *= (1 - PARTIAL_CLOSE_RATIO)
            changed = True
            logger.info(f"[시그널] {reason}")
            tg.notify_partial_close(state.position_side, price, 0)  # PnL 근사값

    # ── 완전 익절 ─────────────────────────────────────────────
    elif sig == Signal.FULL_CLOSE and state.is_open():
        avg = state.avg_price()
        is_long = state.position_side in ("CONTRARIAN_LONG", "TREND_LONG")
        pnl_est = (price - avg) * state.total_qty() if is_long else (avg - price) * state.total_qty()
        close_full(exchange, price, reason)
        tg.notify_close(state.position_side, avg, price, pnl_est, balance, reason)
        state.reset()
        clear_state()
        changed = True
        logger.info(f"[시그널] {reason}")

    return changed


def run(exchange: ccxt.binanceusdm, dry_run: bool = False):
    """
    메인 트레이딩 루프

    Parameters
    ----------
    exchange : 인증된 Binance 클라이언트
    dry_run  : True = 주문 없이 시그널만 로그 출력
    """
    logger.info("=" * 60)
    logger.info("  BTC 선물 라이브 트레이딩 시작")
    logger.info(f"  {'[DRY RUN]' if dry_run else '[실거래 모드]'}")
    logger.info("=" * 60)

    tg.notify_start(dry_run)

    # 시작 초기화
    if not dry_run:
        set_margin_mode(exchange)
        set_leverage(exchange)

    # 이전 포지션 상태 복원
    state = load_state()
    if state.is_open():
        # 바이낸스 실제 포지션과 비교 확인
        real_pos = get_position(exchange)
        if not real_pos:
            logger.warning("[초기화] 저장된 상태 있으나 실제 포지션 없음 → 상태 초기화")
            state.reset()
            clear_state()

    while True:
        try:
            _wait_for_next_candle()

            # ── 캔들 로드 ──────────────────────────────────
            candles = fetch_closed_candles(exchange, TIMEFRAME, CANDLE_LIMIT)
            if len(candles) < BACKTEST_MIN_CANDLES + 10:
                logger.warning(f"[캔들] 부족 ({len(candles)}개) → 건너뜀")
                continue

            # ── 지표 계산 ──────────────────────────────────
            precompute_vol_avg(candles, window=20)
            ema50  = _precompute_ema(candles, 50)
            ema200 = _precompute_ema(candles, 200)

            # 마지막 완성 캔들 기준
            idx    = len(candles) - 1
            candle = candles[idx]
            window = candles[max(0, idx - BACKTEST_WINDOW_SIZE):idx + 1]
            price  = candle["close"]
            macro_down = _is_macro_downtrend(candles, idx, ema50, ema200)

            # ── 추세 롱 하드 손절 체크 ─────────────────────
            if (state.position_side == "TREND_LONG"
                    and state.trend_long_stop > 0
                    and candle["low"] <= state.trend_long_stop):
                logger.warning(
                    f"[손절] 추세롱 저점 ${state.trend_long_stop:,.0f} 이탈 | 현재가: ${price:,.0f}"
                )
                if not dry_run:
                    avg = state.avg_price()
                    pnl_est = (price - avg) * state.total_qty()
                    close_full(exchange, price, "trend_stop_loss")
                    tg.notify_close("TREND_LONG", avg, price, pnl_est,
                                    get_usdt_balance(exchange), "손절")
                    state.reset()
                    clear_state()
                else:
                    logger.info("[DRY RUN] 추세롱 손절 시그널")
                    state.reset()
                continue

            # ── 시그널 생성 ────────────────────────────────
            result = generate_signal(
                candle=candle,
                candles=window,
                position_side=state.position_side,
                martingale_level=state.martingale_level,
                macro_downtrend=macro_down,
            )
            sig    = result.signal
            reason = result.reason

            ts_str = datetime.fromtimestamp(candle["timestamp"] / 1000).strftime("%m/%d %H:%M")
            balance = get_usdt_balance(exchange)
            _log_status(state, balance, price)
            logger.info(f"[{ts_str}] 시그널: {sig.value} — {reason}")

            # ── 주문 실행 ──────────────────────────────────
            if sig == Signal.HOLD:
                continue

            if dry_run:
                logger.info(f"[DRY RUN] 주문 건너뜀: {sig.value}")
                continue

            changed = _handle_signal(
                exchange, sig, reason, state, candle, candles, idx
            )
            if changed:
                save_state(state)

        except KeyboardInterrupt:
            logger.info("\n[종료] Ctrl+C — 루프 종료")
            tg.notify_stop()
            break
        except ccxt.NetworkError as e:
            logger.error(f"[네트워크] 오류: {e} — 30초 후 재시도")
            tg.notify_error(f"네트워크 오류: {e}")
            time.sleep(30)
        except ccxt.ExchangeError as e:
            logger.error(f"[거래소] 오류: {e} — 60초 후 재시도")
            tg.notify_error(f"거래소 오류: {e}")
            time.sleep(60)
        except Exception as e:
            logger.exception(f"[예외] {e} — 30초 후 재시도")
            tg.notify_error(f"예외 발생: {e}")
            time.sleep(30)

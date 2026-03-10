"""
주문 실행 레이어 — 전략 시그널을 실제 바이낸스 주문으로 변환

백테스트 engine.py와 동일한 마틴게일 로직 적용:
  1차 진입: 잔고 × MARTINGALE_PCTS[0] USDT (복리)
  추매    : 잔고 × MARTINGALE_PCTS[level] USDT (복리)
  청산    : reduceOnly 시장가
"""
import logging
import ccxt

from exchange.client import (
    place_market_order, get_usdt_balance,
    get_position, close_all_positions,
)
from config.constants import MARTINGALE_PCTS, MAX_MARTINGALE_LEVEL, PARTIAL_CLOSE_RATIO, MAX_ENTRY_CAPITAL_RATIO

logger = logging.getLogger(__name__)


def enter_long(exchange: ccxt.binanceusdm,
               current_price: float,
               level: int = 0) -> dict | None:
    """
    롱 진입 / 추매

    Parameters
    ----------
    level : 0 = 1차 진입, 1~4 = 마틴게일 추매
    """
    if level >= MAX_MARTINGALE_LEVEL:
        logger.warning(f"[진입] 최대 마틴게일 레벨 초과 ({level})")
        return None

    balance = get_usdt_balance(exchange)
    usdt = balance * MARTINGALE_PCTS[level]

    if usdt > balance * MAX_ENTRY_CAPITAL_RATIO:
        logger.warning(f"[진입] 잔고 부족 (필요: ${usdt:.0f}, 보유: ${balance:.0f}) → 건너뜀")
        return None

    order = place_market_order(exchange, "buy", usdt, current_price)
    if order:
        logger.info(f"[롱 진입] {level+1}차 | ${usdt:.0f} ({MARTINGALE_PCTS[level]*100:.1f}%) | 현재가: ${current_price:,.0f}")
    return order


def enter_short(exchange: ccxt.binanceusdm,
                current_price: float,
                level: int = 0) -> dict | None:
    """
    숏 진입 / 추매

    Parameters
    ----------
    level : 0 = 1차 진입, 1~4 = 마틴게일 추매
    """
    if level >= MAX_MARTINGALE_LEVEL:
        logger.warning(f"[진입] 최대 마틴게일 레벨 초과 ({level})")
        return None

    balance = get_usdt_balance(exchange)
    usdt = balance * MARTINGALE_PCTS[level]

    if usdt > balance * MAX_ENTRY_CAPITAL_RATIO:
        logger.warning(f"[진입] 잔고 부족 (필요: ${usdt:.0f}, 보유: ${balance:.0f}) → 건너뜀")
        return None

    order = place_market_order(exchange, "sell", usdt, current_price)
    if order:
        logger.info(f"[숏 진입] {level+1}차 | ${usdt:.0f} ({MARTINGALE_PCTS[level]*100:.1f}%) | 현재가: ${current_price:,.0f}")
    return order


def close_partial(exchange: ccxt.binanceusdm,
                  current_price: float,
                  position_side: str) -> dict | None:
    """
    분할 익절 (PARTIAL_CLOSE_RATIO 비율만큼 청산)

    position_side: "CONTRARIAN_SHORT" | "CONTRARIAN_LONG" | "TREND_LONG"
    """
    pos = get_position(exchange)
    if not pos:
        logger.warning("[분할익절] 포지션 없음")
        return None

    close_qty = pos["qty"] * PARTIAL_CLOSE_RATIO
    close_qty = round(close_qty, 3)

    close_side = "sell" if pos["side"] == "long" else "buy"
    order = place_market_order(
        exchange, close_side,
        close_qty * current_price,
        current_price,
        reduce_only=True,
    )
    if order:
        logger.info(f"[분할익절] {PARTIAL_CLOSE_RATIO*100:.0f}% 청산 | 현재가: ${current_price:,.0f}")
    return order


def close_full(exchange: ccxt.binanceusdm,
               current_price: float,
               reason: str = "full_close") -> bool:
    """전체 청산"""
    result = close_all_positions(exchange)
    if result:
        logger.info(f"[완전청산] 사유: {reason} | 현재가: ${current_price:,.0f}")
    return result

"""
Binance USD-M Futures 클라이언트 (ccxt 기반)

역할:
  - API 연결 / 인증
  - 잔고 / 포지션 / 캔들 조회
  - 레버리지 설정
  - 시장가 주문 실행

설계 원칙:
  - 모든 예외는 여기서 잡아 로깅 후 None / False 반환
  - 상위 레이어(trader.py)는 None 체크만 하면 됨
"""
import logging
import ccxt

from config.settings import get_api_credentials, is_testnet
from config.constants import SYMBOL, LEVERAGE

logger = logging.getLogger(__name__)

FUTURES_SYMBOL = "BTC/USDT:USDT"   # ccxt USD-M Futures 심볼 형식


def create_client() -> ccxt.binanceusdm:
    """Binance USD-M Futures 클라이언트 생성 (실거래 API)"""
    creds = get_api_credentials()
    exchange = ccxt.binanceusdm({
        "apiKey":          creds["api_key"],
        "secret":          creds["api_secret"],
        "enableRateLimit": True,
        "options": {
            "adjustForTimeDifference": True,
        },
    })
    logger.info("[클라이언트] Binance USD-M Futures 연결")
    return exchange


def check_connection(exchange: ccxt.binanceusdm) -> bool:
    """API 연결 및 인증 확인"""
    try:
        exchange.fetch_balance()
        logger.info("[연결] API 인증 성공")
        return True
    except ccxt.AuthenticationError:
        logger.error("[연결] API 키 인증 실패 — .env 파일 확인")
        return False
    except Exception as e:
        logger.error(f"[연결] 오류: {e}")
        return False


def get_usdt_balance(exchange: ccxt.binanceusdm) -> float:
    """사용 가능한 USDT 잔고 반환"""
    try:
        balance = exchange.fetch_balance()
        return float(balance["USDT"]["free"])
    except Exception as e:
        logger.error(f"[잔고] 조회 실패: {e}")
        return 0.0


def get_position(exchange: ccxt.binanceusdm) -> dict | None:
    """
    현재 BTC/USDT 포지션 반환

    Returns:
        {
          "side": "long" | "short",
          "qty": float,         # BTC 수량 (양수)
          "entry_price": float,
          "unrealized_pnl": float,
          "notional": float,    # USDT 명목금액
        }
        포지션 없으면 None
    """
    try:
        positions = exchange.fetch_positions([FUTURES_SYMBOL])
        for pos in positions:
            contracts = float(pos.get("contracts", 0) or 0)
            if contracts > 0:
                return {
                    "side":           pos["side"],
                    "qty":            contracts,
                    "entry_price":    float(pos["entryPrice"] or 0),
                    "unrealized_pnl": float(pos["unrealizedPnl"] or 0),
                    "notional":       float(pos["notional"] or 0),
                }
        return None
    except Exception as e:
        logger.error(f"[포지션] 조회 실패: {e}")
        return None


def set_leverage(exchange: ccxt.binanceusdm, leverage: int = LEVERAGE) -> bool:
    """레버리지 설정"""
    try:
        exchange.set_leverage(leverage, FUTURES_SYMBOL)
        logger.info(f"[레버리지] {leverage}x 설정 완료")
        return True
    except Exception as e:
        logger.error(f"[레버리지] 설정 실패: {e}")
        return False


def set_margin_mode(exchange: ccxt.binanceusdm, mode: str = "isolated") -> bool:
    """마진 모드 설정 (isolated 권장 — 포지션별 독립 리스크)"""
    try:
        exchange.set_margin_mode(mode, FUTURES_SYMBOL)
        logger.info(f"[마진모드] {mode} 설정 완료")
        return True
    except ccxt.MarginModeAlreadySet:
        return True   # 이미 설정됨
    except Exception as e:
        logger.warning(f"[마진모드] 설정 경고 (무시 가능): {e}")
        return True


def fetch_closed_candles(exchange: ccxt.binanceusdm,
                         timeframe: str = "5m",
                         limit: int = 250) -> list:
    """
    완성된 캔들 리스트 반환 (현재 진행 중인 마지막 캔들 제외)

    Returns:
        [{"timestamp": ms, "open": float, "high": float,
          "low": float, "close": float, "volume": float}, ...]
    """
    try:
        raw = exchange.fetch_ohlcv(FUTURES_SYMBOL, timeframe, limit=limit + 1)
        if not raw or len(raw) < 2:
            return []
        # 마지막 캔들은 현재 진행 중 → 제외
        closed = raw[:-1]
        return [
            {
                "timestamp":    c[0],
                "open":         float(c[1]),
                "high":         float(c[2]),
                "low":          float(c[3]),
                "close":        float(c[4]),
                "volume":       float(c[5]),
                "quote_volume": float(c[5]) * float(c[4]),  # 근사값
            }
            for c in closed
        ]
    except Exception as e:
        logger.error(f"[캔들] 조회 실패: {e}")
        return []


def place_market_order(exchange: ccxt.binanceusdm,
                       side: str,
                       usdt_amount: float,
                       current_price: float,
                       reduce_only: bool = False) -> dict | None:
    """
    시장가 주문 실행

    Parameters
    ----------
    side          : "buy" | "sell"
    usdt_amount   : 주문할 USDT 금액 (레버리지 미적용 명목금액)
    current_price : 현재가 (수량 계산용)
    reduce_only   : True = 청산 전용 주문

    Returns
    -------
    주문 결과 dict | 실패 시 None
    """
    try:
        # 수량 계산: USDT / 현재가 = BTC 수량
        # ccxt는 계약 수량(BTC) 단위로 주문
        qty = usdt_amount / current_price
        qty = exchange.amount_to_precision(FUTURES_SYMBOL, qty)

        params = {}
        if reduce_only:
            params["reduceOnly"] = True

        order = exchange.create_market_order(
            FUTURES_SYMBOL, side, float(qty), params=params
        )
        filled_price = float(order.get("average") or current_price)
        logger.info(
            f"[주문] {side.upper()} {qty} BTC @ ${filled_price:,.0f} "
            f"(USDT: ${usdt_amount:.0f})"
        )
        return order
    except ccxt.InsufficientFunds:
        logger.error(f"[주문] 잔고 부족 — 주문 취소")
        return None
    except Exception as e:
        logger.error(f"[주문] 실패: {e}")
        return None


def close_all_positions(exchange: ccxt.binanceusdm) -> bool:
    """현재 포지션 전체 청산 (긴급 스탑용)"""
    pos = get_position(exchange)
    if not pos:
        logger.info("[긴급청산] 포지션 없음")
        return True
    close_side = "sell" if pos["side"] == "long" else "buy"
    try:
        exchange.create_market_order(
            FUTURES_SYMBOL, close_side, pos["qty"],
            params={"reduceOnly": True}
        )
        logger.warning(f"[긴급청산] {pos['side']} {pos['qty']} BTC 전체 청산")
        return True
    except Exception as e:
        logger.error(f"[긴급청산] 실패: {e}")
        return False

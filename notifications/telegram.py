"""
텔레그램 알림 모듈

requests로 Bot API 직접 호출 (python-telegram-bot 불필요, 간단하고 동기식)

봇 설정 방법:
  1. 텔레그램에서 @BotFather 검색 → /newbot → 토큰 발급
  2. 봇에게 메시지 한 번 보내기
  3. https://api.telegram.org/bot<TOKEN>/getUpdates 에서 chat_id 확인
  4. .env 파일에 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 입력
"""
import logging
import os
import requests
from datetime import datetime

from config.settings import get_telegram_credentials

logger = logging.getLogger(__name__)

_CREDS = None   # 초기화 지연 (import 시 .env 미로드 방지)


def _get_creds():
    global _CREDS
    if _CREDS is None:
        _CREDS = get_telegram_credentials()
    return _CREDS


def _send(text: str) -> bool:
    """텔레그램 메시지 전송. 실패 시 로그만 남기고 False 반환."""
    creds = _get_creds()
    if not creds["token"] or not creds["chat_id"]:
        return False   # 설정 안 됨 → 조용히 스킵
    try:
        url = f"https://api.telegram.org/bot{creds['token']}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": creds["chat_id"], "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"[텔레그램] 전송 실패 (무시): {e}")
        return False


# ── 공개 API ────────────────────────────────────────────────

def notify_enter(side: str, level: int, price: float,
                 usdt: float, balance: float):
    """
    진입 / 추매 알림

    side  : "CONTRARIAN_SHORT" | "CONTRARIAN_LONG" | "TREND_LONG"
    level : 1 = 1차 진입, 2~5 = 추매
    """
    emoji = {"CONTRARIAN_SHORT": "🔴", "CONTRARIAN_LONG": "🟢", "TREND_LONG": "🚀"}.get(side, "⚪")
    label = {"CONTRARIAN_SHORT": "역추세 숏", "CONTRARIAN_LONG": "역추세 롱", "TREND_LONG": "추세 롱"}.get(side, side)
    action = "진입" if level == 1 else f"{level}차 추매"

    _send(
        f"{emoji} <b>{label} {action}</b>\n"
        f"${usdt:.0f} | @ <b>${price:,.0f}</b>\n"
        f"잔고: ${balance:.0f}"
    )


def notify_close(side: str, entry_price: float, exit_price: float,
                 pnl: float, balance: float, reason: str = ""):
    """익절 / 손절 알림"""
    is_profit = pnl >= 0
    emoji = "✅" if is_profit else "🛑"
    pnl_str = f"+${pnl:.2f}" if is_profit else f"-${abs(pnl):.2f}"
    label = {"CONTRARIAN_SHORT": "역추세 숏", "CONTRARIAN_LONG": "역추세 롱", "TREND_LONG": "추세 롱"}.get(side, side)

    _send(
        f"{emoji} <b>{label} 청산</b>  {reason}\n"
        f"진입가: ${entry_price:,.0f} → 청산가: ${exit_price:,.0f}\n"
        f"PnL: <b>{pnl_str}</b> | 잔고: ${balance:.0f}"
    )


def notify_partial_close(side: str, price: float, pnl: float):
    """분할 익절 알림"""
    label = {"CONTRARIAN_SHORT": "역추세 숏", "CONTRARIAN_LONG": "역추세 롱"}.get(side, side)
    _send(
        f"🔁 <b>{label} 분할익절</b>\n"
        f"@ ${price:,.0f} | PnL: +${pnl:.2f}"
    )


def notify_error(error: str):
    """에러 알림"""
    _send(f"⚠️ <b>오류 발생</b>\n{error[:300]}")


def notify_start(dry_run: bool = False):
    """봇 시작 알림"""
    dr = " [DRY RUN]" if dry_run else ""
    _send(
        f"🤖 <b>BTC 선물봇 시작</b>{dr}\n"
        f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


def notify_stop():
    """봇 종료 알림"""
    _send(f"🔌 BTC 선물봇 종료 ({datetime.now().strftime('%H:%M')})")


def notify_morning_report(equity: float, daily_pnl: float, trade_count: int) -> None:
    """매일 오전 9시 KST 현황 보고"""
    from datetime import timezone, timedelta
    kst = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%m/%d %H:%M")
    pnl_str = f"+${daily_pnl:,.2f}" if daily_pnl >= 0 else f"-${abs(daily_pnl):,.2f}"
    _send(
        f"☀️ <b>아침 보고 (BTC봇)</b>  {kst} KST\n"
        f"잔고: <b>${equity:,.0f}</b>  |  오늘 PnL: {pnl_str} ({trade_count}회)"
    )


def notify_daily_summary(balance: float, today_trades: int,
                         today_pnl: float, total_withdrawn: float):
    """일일 요약 알림 (선택적 사용)"""
    pnl_str = f"+${today_pnl:.2f}" if today_pnl >= 0 else f"-${abs(today_pnl):.2f}"
    _send(
        f"📊 <b>일일 요약</b>  {datetime.now().strftime('%Y-%m-%d')}\n"
        f"잔고: ${balance:.0f} | 오늘 거래: {today_trades}회\n"
        f"오늘 PnL: {pnl_str} | 누적 출금: ${total_withdrawn:.0f}"
    )

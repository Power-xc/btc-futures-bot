"""
시그널 생성 — State Machine

포지션 종류:
  CONTRARIAN_SHORT : 역추세 숏 (가짜 상승 페이드)
  CONTRARIAN_LONG  : 역추세 롱 (가짜 하락 페이드)
  TREND_LONG       : 추세 롱 (거래량 1K+ 돌파 추종)
  None             : 미보유
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional

from strategy.patterns import (
    is_fake_pump, is_fake_dump,
    is_trend_long_entry, is_trend_continuation, is_trend_long_exit,
    is_spike_up, is_spike_down,
    is_staircase,
    is_strong_move_down,
    is_volume_exhaustion,
)
from config.constants import MAX_MARTINGALE_LEVEL


class Signal(Enum):
    # 신규 진입
    ENTER_CONTRARIAN_SHORT = "enter_c_short"
    ENTER_CONTRARIAN_LONG  = "enter_c_long"
    ENTER_TREND_LONG       = "enter_t_long"
    # 추매
    ADD_SHORT = "add_short"
    ADD_LONG  = "add_long"
    # 익절
    PARTIAL_CLOSE = "partial_close"
    FULL_CLOSE    = "full_close"
    # 유지
    HOLD = "hold"


@dataclass
class SignalResult:
    signal: Signal
    reason: str


def generate_signal(
    candle: dict,
    candles: list,
    position_side: Optional[str] = None,
    martingale_level: int = 0,
    macro_downtrend: bool = False,
) -> SignalResult:
    """
    position_side 값:
      None              → 미보유
      "CONTRARIAN_SHORT"
      "CONTRARIAN_LONG"
      "TREND_LONG"

    macro_downtrend: 엔진에서 EMA1440/4320으로 사전 계산된 매크로 하락추세 여부
    """
    downtrend = macro_downtrend

    # ── IDLE ──────────────────────────────────────────────
    # 핵심 원칙: 볼륨이 진실 탐지기
    #   양봉 + 거래량 있음 → 진짜 상승 → 추세 롱
    #   양봉 + 거래량 없음 → 가짜 상승 → 역추세 숏 (분할)
    #   음봉 + 거래량 없음 → 가짜 하락 → 역추세 롱 (하락추세 시 차단)
    if position_side is None:
        if is_trend_long_entry(candle) and not downtrend:
            return SignalResult(Signal.ENTER_TREND_LONG, "거래량 1K+ 양봉 + 상승추세 → 추세 롱 진입")
        if is_fake_pump(candle):
            return SignalResult(Signal.ENTER_CONTRARIAN_SHORT, "거래량 없는 상승 → 역추세 숏 진입")
        if is_fake_dump(candle) and not downtrend:
            return SignalResult(Signal.ENTER_CONTRARIAN_LONG, "거래량 없는 하락 + 상승추세 → 역추세 롱 진입")
        return SignalResult(Signal.HOLD, "진입 조건 없음")

    # ── 역추세 숏 ─────────────────────────────────────────
    # 순환 매매: 손절/스위칭 없음 — 가짜 펌프는 결국 되돌아온다
    # 진짜 원웨이 무빙에는 마틴게일 소진 후 청산 (리스크는 출금으로 관리)
    if position_side == "CONTRARIAN_SHORT":
        if is_staircase(candles):
            return SignalResult(Signal.HOLD, "계단식 → 홀딩")
        if is_spike_down(candles):
            if is_volume_exhaustion(candles):
                return SignalResult(Signal.FULL_CLOSE, "거래량 소멸 + 하락 피뢰침 → 숏 완익")
            return SignalResult(Signal.PARTIAL_CLOSE, "하락 피뢰침 → 숏 분할익절")
        if is_spike_up(candles) and martingale_level < MAX_MARTINGALE_LEVEL:
            return SignalResult(Signal.ADD_SHORT, f"거래량 없는 상승 피뢰침 → 숏 {martingale_level+1}차 추매")
        return SignalResult(Signal.HOLD, "홀딩")

    # ── 역추세 롱 ─────────────────────────────────────────
    if position_side == "CONTRARIAN_LONG":
        if is_strong_move_down(candle):
            return SignalResult(Signal.FULL_CLOSE, "강한 음봉 → 역추세 롱 손절 청산")
        if is_staircase(candles):
            return SignalResult(Signal.HOLD, "계단식 → 홀딩")
        if is_spike_up(candles):
            if is_volume_exhaustion(candles):
                return SignalResult(Signal.FULL_CLOSE, "거래량 소멸 + 상승 피뢰침 → 롱 완익")
            return SignalResult(Signal.PARTIAL_CLOSE, "상승 피뢰침 → 롱 분할익절")
        if is_spike_down(candles) and martingale_level < MAX_MARTINGALE_LEVEL:
            return SignalResult(Signal.ADD_LONG, f"거래량 없는 하락 피뢰침 → 롱 {martingale_level+1}차 추매")
        return SignalResult(Signal.HOLD, "홀딩")

    # ── 추세 롱 ───────────────────────────────────────────
    if position_side == "TREND_LONG":
        if is_trend_long_exit(candle):
            return SignalResult(Signal.FULL_CLOSE, "강한 음봉 구조 → 추세 롱 청산")
        if is_trend_continuation(candle):
            return SignalResult(Signal.HOLD, "거래량 지속 → 추세 홀딩 (다음 파동 대기)")
        # 거래량 소멸 + 약세 신호
        if is_volume_exhaustion(candles):
            return SignalResult(Signal.FULL_CLOSE, "거래량 소멸 → 추세 롱 청산")
        return SignalResult(Signal.HOLD, "홀딩")

    return SignalResult(Signal.HOLD, "알 수 없는 상태")

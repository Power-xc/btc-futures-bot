"""
패턴 감지 — 상대 거래량(vol_avg) 기준, BTC 절대값 폴백
"""
from strategy.indicators import (
    is_bullish, is_bearish,
    calc_body_pct, calc_body_range_ratio,
    calc_upper_wick_ratio, calc_lower_wick_ratio,
    is_volume_weak, is_volume_strong, is_volume_trend,
)
from config.constants import (
    FAKE_MOVE_BODY_PCT, FAKE_MOVE_BODY_RATIO,
    SPIKE_BODY_PCT, SPIKE_WICK_MIN_RATIO, SPIKE_CLUSTER_MOVE_PCT,
    STAIRCASE_LOOKBACK, STAIRCASE_MAX_BODY_PCT, STAIRCASE_MIN_COUNT,
    VOL_EXHAUST_LOOKBACK, VOL_EXHAUST_DROP_RATIO,
    TREND_CONTINUATION_BTC, STRONG_BEARISH_BODY_PCT,
)


# ── 역추세 진입 (가짜 움직임) ──────────────────────────────

def is_fake_pump(candle: dict) -> bool:
    """가짜 급등 → 숏 진입
    조건: 양봉 + 큰 몸통 + 거래량 미달 (vol_avg 기준)
    """
    return (
        is_bullish(candle)
        and calc_body_pct(candle) >= FAKE_MOVE_BODY_PCT
        and calc_body_range_ratio(candle) >= FAKE_MOVE_BODY_RATIO
        and is_volume_weak(candle)
    )


def is_fake_dump(candle: dict) -> bool:
    """가짜 급락 → 역추세 롱 진입
    조건: 음봉 + 큰 몸통 + 거래량 미달 (vol_avg 기준)
    """
    return (
        is_bearish(candle)
        and calc_body_pct(candle) >= FAKE_MOVE_BODY_PCT
        and calc_body_range_ratio(candle) >= FAKE_MOVE_BODY_RATIO
        and is_volume_weak(candle)
    )


# ── 추세 롱 진입 ───────────────────────────────────────────

def is_trend_long_entry(candle: dict) -> bool:
    """추세 롱 진입
    조건: 양봉 + 거래량 3x 이상 (vol_avg 기준, 진짜 매수세)
    """
    return (
        is_bullish(candle)
        and is_volume_trend(candle)
        and calc_body_pct(candle) >= FAKE_MOVE_BODY_PCT
    )


def is_trend_continuation(candle: dict) -> bool:
    """추세 지속 = 홀딩 유지
    거래량이 계속 높게 유지됨 (= 다음 파동 오기 전까지 홀딩)
    """
    return candle["volume"] >= TREND_CONTINUATION_BTC


def is_trend_long_exit(candle: dict) -> bool:
    """추세 롱 청산 신호 (파동 종료 확인)
    조건: 음봉 + 강한 구조 + 실제 매도 거래량 동반
    → 파동 중 일반 되돌림 음봉(거래량 없음)에 청산하지 않기 위해 거래량 필터 추가
    """
    return (
        is_bearish(candle)
        and calc_body_pct(candle) >= FAKE_MOVE_BODY_PCT
        and calc_body_range_ratio(candle) >= FAKE_MOVE_BODY_RATIO
        and is_volume_trend(candle)   # 3x+ 매도 = 진짜 반전
    )


# ── 피뢰침 (추매 / 분할익절 트리거) ───────────────────────
# 피뢰침 = 단일 캔들 OR 2-3 캔들 클러스터가 한 방향으로 급격히 이동 후 일부 되돌림
# 계단식과 차이: 계단식은 개별 캔들 몸통이 작은 완만한 흐름,
#               피뢰침은 클러스터 전체 이동이 SPIKE_CLUSTER_MOVE_PCT 이상인 급격한 움직임

def _cluster_spike_up(candles: list) -> bool:
    """상승 클러스터 피뢰침 내부 로직 (2-3 캔들, 거래량 미달 필수)"""
    cluster = candles[-3:]
    cluster_start_open = cluster[0]["open"]
    current_close = candles[-1]["close"]
    cluster_high = 0.0
    for c in cluster:
        if c["high"] > cluster_high:
            cluster_high = c["high"]
        if not is_volume_weak(c):
            return False   # 거래량 있는 캔들 발견 → 즉시 False
    meaningful_move = (cluster_high - cluster_start_open) / cluster_start_open >= SPIKE_CLUSTER_MOVE_PCT
    spike_then_retrace = (cluster_high - current_close) / current_close >= SPIKE_BODY_PCT
    return meaningful_move and spike_then_retrace


def _cluster_spike_down(candles: list) -> bool:
    """하락 클러스터 피뢰침 내부 로직 (2-3 캔들, 거래량 체크 없음)"""
    cluster = candles[-3:]
    cluster_start_open = cluster[0]["open"]
    current_close = candles[-1]["close"]
    cluster_low = float("inf")
    for c in cluster:
        if c["low"] < cluster_low:
            cluster_low = c["low"]
    meaningful_move = (cluster_start_open - cluster_low) / cluster_start_open >= SPIKE_CLUSTER_MOVE_PCT
    spike_then_retrace = (current_close - cluster_low) / cluster_low >= SPIKE_BODY_PCT
    return meaningful_move and spike_then_retrace


def is_spike_up(candles: list) -> bool:
    """상승 피뢰침 (단일 캔들 or 2-3 캔들 클러스터) + 거래량 미달
    숏 보유 중 → 추매 / 롱 보유 중 → 분할익절
    """
    if not candles:
        return False
    candle = candles[-1]
    single_spike = (
        (is_bullish(candle) and calc_body_pct(candle) >= SPIKE_BODY_PCT)
        or calc_upper_wick_ratio(candle) >= SPIKE_WICK_MIN_RATIO
    ) and is_volume_weak(candle)
    if single_spike:
        return True
    return len(candles) >= 2 and _cluster_spike_up(candles)


def is_spike_down(candles: list) -> bool:
    """하락 피뢰침 (단일 캔들 or 2-3 캔들 클러스터) + 거래량 미달
    롱 보유 중 → 추매 / 숏 보유 중 → 분할익절
    """
    if not candles:
        return False
    candle = candles[-1]
    single_spike = (
        (is_bearish(candle) and calc_body_pct(candle) >= SPIKE_BODY_PCT)
        or calc_lower_wick_ratio(candle) >= SPIKE_WICK_MIN_RATIO
    ) and is_volume_weak(candle)
    if single_spike:
        return True
    return len(candles) >= 2 and _cluster_spike_down(candles)


# ── 계단식 (홀딩) ──────────────────────────────────────────

def is_staircase(candles: list) -> bool:
    """계단식 움직임 = 홀딩 (추매/익절 없음)"""
    recent = candles[-STAIRCASE_LOOKBACK:]
    small_count = sum(1 for c in recent if calc_body_pct(c) < STAIRCASE_MAX_BODY_PCT)
    return small_count >= STAIRCASE_MIN_COUNT


# ── 강한 캔들 손절 트리거 ──────────────────────────────────

def is_strong_move_down(candle: dict) -> bool:
    """강한 음봉 → 롱 손절 트리거
    하락 거래량 무시 — 음봉 몸통 1.2% 이상 + 몸통비율 65% 이상으로 판단
    """
    return (
        is_bearish(candle)
        and calc_body_pct(candle) >= STRONG_BEARISH_BODY_PCT
        and calc_body_range_ratio(candle) >= FAKE_MOVE_BODY_RATIO
    )


# ── 거래량 소멸 (완익) ─────────────────────────────────────

def is_volume_exhaustion(candles: list) -> bool:
    """거래량 소멸 = 완익 신호
    큰 이동 후 최근 N봉 평균 거래량이 직전 피크 대비 급감
    """
    if len(candles) < VOL_EXHAUST_LOOKBACK + 5:
        return False
    recent = candles[-VOL_EXHAUST_LOOKBACK:]
    peak_window = candles[-(VOL_EXHAUST_LOOKBACK + 5):-VOL_EXHAUST_LOOKBACK]
    peak_vol = max((c["volume"] for c in peak_window), default=0)
    if peak_vol == 0:
        return False
    avg_recent = sum(c["volume"] for c in recent) / len(recent)
    return avg_recent < peak_vol * VOL_EXHAUST_DROP_RATIO

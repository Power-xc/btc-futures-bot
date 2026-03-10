"""
저수준 지표 계산 — 거래량 상대값 기준
- 캔들에 vol_avg(최근 20봉 평균)가 있으면 상대 비율로 판단
- 없으면 절대값(BTC) 폴백 (하위 호환)

상대 비율 기준 (시대·시장 무관하게 동일하게 작동):
  weak   = 최근 평균의 70% 미만   (VOL_WEAK_RATIO=0.70)
  trend  = 최근 평균의 300% 이상  (VOL_TREND_RATIO=3.00, 3x 스파이크)
  strong = 최근 평균의 600% 이상  (VOL_STRONG_RATIO=6.00, 6x 스파이크)
"""
from config.constants import VOLUME_STRONG_BTC, VOLUME_WEAK_BTC, VOLUME_TREND_BTC

VOL_WEAK_RATIO   = 0.92   # < 92% of avg → 거래량 미달 (2차 최적화: 0.70→0.92)
VOL_TREND_RATIO  = 3.50   # > 350% of avg (3.5x) → 추세 진입 (2차 최적화: 3.00→3.50)
VOL_STRONG_RATIO = 6.00   # > 600% of avg (6x 스파이크) → 극강 거래량


def is_volume_weak(candle: dict) -> bool:
    """거래량 미달 = 가짜 움직임 (상대 기준 우선)"""
    if "vol_avg" in candle and candle["vol_avg"] > 0:
        return candle["volume"] < candle["vol_avg"] * VOL_WEAK_RATIO
    return candle["volume"] < VOLUME_WEAK_BTC


def is_volume_strong(candle: dict) -> bool:
    """극강 거래량 (상대 기준 우선)"""
    if "vol_avg" in candle and candle["vol_avg"] > 0:
        return candle["volume"] >= candle["vol_avg"] * VOL_STRONG_RATIO
    return candle["volume"] >= VOLUME_STRONG_BTC


def is_volume_trend(candle: dict) -> bool:
    """추세 진입 거래량 (상대 기준 우선)"""
    if "vol_avg" in candle and candle["vol_avg"] > 0:
        return candle["volume"] >= candle["vol_avg"] * VOL_TREND_RATIO
    return candle["volume"] >= VOLUME_TREND_BTC


def is_bullish(candle: dict) -> bool:
    return candle["close"] > candle["open"]


def is_bearish(candle: dict) -> bool:
    return candle["close"] < candle["open"]


def calc_body_pct(candle: dict) -> float:
    return abs(candle["close"] - candle["open"]) / candle["open"]


def calc_body_range_ratio(candle: dict) -> float:
    total = candle["high"] - candle["low"]
    if total == 0:
        return 0.0
    return abs(candle["close"] - candle["open"]) / total


def calc_upper_wick_ratio(candle: dict) -> float:
    total = candle["high"] - candle["low"]
    if total == 0:
        return 0.0
    return (candle["high"] - max(candle["open"], candle["close"])) / total


def calc_lower_wick_ratio(candle: dict) -> float:
    total = candle["high"] - candle["low"]
    if total == 0:
        return 0.0
    return (min(candle["open"], candle["close"]) - candle["low"]) / total

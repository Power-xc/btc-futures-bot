"""EMA (지수이동평균) 사전 계산 유틸"""


def precompute_ema(candles: list, period: int) -> list:
    """전체 캔들에 대한 EMA 배열 반환 (인덱스 일치)"""
    k = 2 / (period + 1)
    ema = [candles[0]["close"]]
    for c in candles[1:]:
        ema.append(c["close"] * k + ema[-1] * (1 - k))
    return ema

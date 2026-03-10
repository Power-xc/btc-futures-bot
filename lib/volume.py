"""
거래량 평균(vol_avg) 사전 계산

슬라이딩 윈도우로 각 캔들에 vol_avg 필드를 인플레이스 추가.
engine.py와 분석 스크립트 모두에서 import해서 재사용.
"""
from collections import deque


def precompute_vol_avg(candles: list, window: int = 20) -> None:
    """
    캔들 리스트 각 항목에 ``vol_avg`` 키를 인플레이스로 추가.

    vol_avg = 현재 캔들을 제외한 직전 window봉 평균 거래량
    (현재 캔들 포함하지 않아 미래 정보 사용 방지)

    O(n) 슬라이딩 윈도우 — 7년 73만 캔들도 빠르게 처리.

    Parameters
    ----------
    candles : list of candle dict (volume 키 필요)
    window  : 평균 계산 구간 (기본 20봉, 최적화 검증 완료)
    """
    q: deque = deque()
    running_sum = 0.0

    for candle in candles:
        n_past = len(q)
        candle["vol_avg"] = running_sum / n_past if n_past > 0 else candle["volume"]
        vol = candle["volume"]
        running_sum += vol
        q.append(vol)
        if len(q) > window:
            running_sum -= q.popleft()

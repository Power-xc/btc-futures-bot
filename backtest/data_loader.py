"""
과거 데이터 수집 (바이낸스 현물 공개 API)
- 페이지네이션으로 장기 데이터 수집
- CSV 캐시 저장
"""
import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime

from config.constants import SYMBOL, DATA_DIR, SPOT_BASE_URL

logger = logging.getLogger(__name__)

KLINES_LIMIT = 1000       # 바이낸스 현물 API 최대
RATE_LIMIT_SLEEP = 0.3


def _timeframe_to_ms(timeframe: str) -> int:
    mapping = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000,
        "15m": 900_000, "30m": 1_800_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    return mapping.get(timeframe, 300_000)


def _fetch_batch(timeframe: str, start_ms: int, end_ms: int) -> list:
    url = f"{SPOT_BASE_URL}/api/v3/klines"
    params = {
        "symbol": SYMBOL, "interval": timeframe,
        "startTime": start_ms, "endTime": end_ms, "limit": KLINES_LIMIT,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"API 요청 실패: {e}")
        return []


def fetch_historical_data(
    timeframe: str = "5m",
    start_date: str = "2024-01-01",
    end_date: str = "2025-01-01",
    use_cache: bool = True,
) -> pd.DataFrame:
    os.makedirs(DATA_DIR, exist_ok=True)
    cache_path = os.path.join(DATA_DIR, f"BTCUSDT_spot_{timeframe}_{start_date}_{end_date}.csv")

    if use_cache and os.path.exists(cache_path):
        logger.info(f"캐시 로드: {cache_path}")
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        logger.info(f"캔들 {len(df):,}개 로드")
        return df

    logger.info(f"다운로드: {start_date} ~ {end_date} ({timeframe})")
    start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
    interval_ms = _timeframe_to_ms(timeframe)
    total_expected = (end_ms - start_ms) // interval_ms
    logger.info(f"예상 캔들: {total_expected:,}개")

    all_rows = []
    current_ms = start_ms

    while current_ms < end_ms:
        batch = _fetch_batch(timeframe, current_ms, end_ms)
        if not batch:
            break
        all_rows.extend(batch)
        current_ms = batch[-1][0] + interval_ms
        progress = min(len(all_rows) / total_expected * 100, 100)
        logger.info(f"  {len(all_rows):,}개 ({progress:.1f}%)")
        time.sleep(RATE_LIMIT_SLEEP)
        if len(batch) < KLINES_LIMIT:
            break

    if not all_rows:
        logger.error("데이터 없음")
        return pd.DataFrame()

    df = _parse_klines(all_rows)
    df.to_csv(cache_path)
    logger.info(f"캐시 저장: {cache_path} ({len(df):,}개)")
    return df


def _parse_klines(raw: list) -> pd.DataFrame:
    cols = ["open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df = df[["open", "high", "low", "close", "volume", "quote_volume"]]
    df.sort_index(inplace=True)
    return df[~df.index.duplicated(keep="first")]


def load_as_candle_list(df: pd.DataFrame) -> list:
    candles = []
    for ts, row in df.iterrows():
        candles.append({
            "timestamp": int(ts.timestamp() * 1000),
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"],
            "volume": row["volume"], "quote_volume": row["quote_volume"],
        })
    return candles

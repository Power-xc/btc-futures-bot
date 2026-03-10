#!/usr/bin/env python3
"""
백테스트 실행 스크립트

사용법:
  python run_backtest.py --start 2022-01-01 --end 2025-01-01
  python run_backtest.py --start 2022-01-01 --end 2025-01-01 --no-cache
"""
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.data_loader import fetch_historical_data, load_as_candle_list
from backtest.engine import run_backtest
from backtest.report import generate_report
from config.constants import INITIAL_CAPITAL


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="BTC 선물 백테스트 (숏/롱 마틴게일 + 추세롱)")
    parser.add_argument("--start",   default="2022-01-01")
    parser.add_argument("--end",     default="2025-01-01")
    parser.add_argument("--tf",      default="5m")
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--verbose",  action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("  BTC 선물 백테스트 — 역추세(숏/롱) + 추세 롱 전략")
    logger.info(f"  기간: {args.start} ~ {args.end} | 봉: {args.tf}")
    from config.constants import LEVERAGE, MARTINGALE_AMOUNTS
    mart_str = "/".join(f"${a}" for a in MARTINGALE_AMOUNTS)
    logger.info(f"  초기 자본: ${args.capital:,.0f} | 레버리지: {LEVERAGE}x")
    logger.info(f"  마틴게일: {mart_str} (×2.5배수)")
    logger.info("=" * 60)

    df = fetch_historical_data(
        timeframe=args.tf,
        start_date=args.start,
        end_date=args.end,
        use_cache=not args.no_cache,
    )
    if df.empty:
        logger.error("데이터 없음. 종료.")
        return

    candles = load_as_candle_list(df)
    logger.info(f"캔들 {len(candles):,}개 준비")

    trades, equity_curve, withdrawals, stage_log = run_backtest(
        candles, initial_capital=args.capital
    )

    generate_report(trades, equity_curve, withdrawals, stage_log)
    print("결과 파일: results/ 폴더 확인\n")


if __name__ == "__main__":
    main()

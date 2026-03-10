#!/usr/bin/env python3
"""
라이브 트레이딩 실행 스크립트

사용법:
  # 테스트넷 + 드라이런 (주문 없이 시그널만 확인)
  python run_live.py --dry-run

  # 테스트넷 실제 주문
  python run_live.py

  # 실거래 (.env의 USE_TESTNET=false 필요)
  python run_live.py

시작 전 체크리스트:
  1. .env 파일 생성 (.env.example 참고)
  2. BINANCE_API_KEY, BINANCE_API_SECRET 입력
  3. USE_TESTNET=true 로 먼저 테스트
  4. 잔고 확인: 최소 $100 이상 권장 (마틴게일 1차 진입 $15 기준)
"""
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exchange.client import create_client, check_connection
from core.trader import run
from config.settings import is_testnet


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt   = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    # ccxt 로그 레벨 낮춤 (너무 장황함)
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="BTC 선물 라이브 트레이딩 — 역추세(숏/롱) + 추세 롱",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="주문 없이 시그널만 출력 (기본: 실제 주문)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="디버그 로그 출력",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # ── 환경 확인 ──────────────────────────────────────────
    testnet = is_testnet()
    logger.info("=" * 60)
    logger.info("  BTC 선물 자동매매 봇")
    logger.info(f"  모드: {'테스트넷' if testnet else '★ 실거래 ★'}")
    logger.info(f"  {'[DRY RUN] 주문 없음' if args.dry_run else '주문 실행됨'}")
    logger.info("=" * 60)

    if not testnet and not args.dry_run:
        confirm = input("\n★ 실거래 모드입니다. 계속하시겠습니까? (yes 입력): ")
        if confirm.strip().lower() != "yes":
            logger.info("취소됨.")
            return

    # ── API 연결 ───────────────────────────────────────────
    exchange = create_client()
    if not check_connection(exchange):
        logger.error(".env 파일의 API 키를 확인하세요.")
        sys.exit(1)

    # ── 트레이딩 루프 시작 ─────────────────────────────────
    run(exchange, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

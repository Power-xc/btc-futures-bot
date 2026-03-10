#!/usr/bin/env python3
"""
라이브 트레이딩 실행 스크립트

사용법:
  # 드라이런 (주문 없이 시그널만 확인 — 처음 시작 시 필수)
  python run_live.py --dry-run

  # 실거래 (실제 주문 실행)
  python run_live.py

시작 전 체크리스트:
  1. .env 파일 생성 (.env.example 참고)
  2. BINANCE_API_KEY, BINANCE_API_SECRET 입력
     - 바이낸스 > API Management > 선물 거래 권한 체크
  3. python run_live.py --dry-run 으로 연결 + 시그널 먼저 확인
  4. 잔고 확인: 최소 $200 이상 권장 (마틴게일 최대 $981 노출)
"""
import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exchange.client import create_client, check_connection
from core.trader import run


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt   = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(
        description="BTC 선물 라이브 트레이딩 — 역추세(숏/롱) + 추세 롱",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="주문 없이 시그널만 출력",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="디버그 로그 출력",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="실거래 확인 프롬프트 생략 (systemd 등 비대화형 환경용)",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("  BTC 선물 자동매매 봇")
    logger.info(f"  {'[DRY RUN] 주문 없음' if args.dry_run else '★ 실거래 — 실제 주문 실행 ★'}")
    logger.info("=" * 60)

    if not args.dry_run and not args.yes:
        confirm = input("\n★ 실제 주문이 실행됩니다. 계속하시겠습니까? (yes 입력): ")
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

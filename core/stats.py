"""
거래 통계 추적

실현 PnL, 거래 횟수, 승률을 JSON 파일로 영구 저장.
봇 재시작 시에도 누적 데이터 유지.
"""
import json
import logging
import os
from datetime import date

logger = logging.getLogger(__name__)

STATS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "stats.json")


def _default() -> dict:
    return {
        "total_pnl":    0.0,
        "today_pnl":    0.0,
        "today_date":   str(date.today()),
        "total_trades": 0,
        "wins":         0,
    }


def load_stats() -> dict:
    try:
        with open(STATS_FILE) as f:
            stats = json.load(f)
        if stats.get("today_date") != str(date.today()):
            stats["today_pnl"]  = 0.0
            stats["today_date"] = str(date.today())
            save_stats(stats)
        return stats
    except (FileNotFoundError, json.JSONDecodeError):
        return _default()


def save_stats(stats: dict):
    os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def record_trade(pnl: float) -> dict:
    """거래 1건 기록 후 업데이트된 stats 반환"""
    stats = load_stats()
    stats["total_pnl"]    += pnl
    stats["today_pnl"]    += pnl
    stats["total_trades"] += 1
    if pnl > 0:
        stats["wins"] += 1
    save_stats(stats)
    logger.info(f"[통계] PnL {pnl:+.2f} | 누적 {stats['total_pnl']:+.2f} | "
                f"{stats['wins']}/{stats['total_trades']}승")
    return stats

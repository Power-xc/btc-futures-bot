"""
포지션 상태 관리

trader.py가 포지션 상태를 JSON 파일로 저장/복원.
프로세스 재시작 시 이전 포지션 상태를 복원해 거래 연속성 유지.
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "state.json")


@dataclass
class Entry:
    """마틴게일 진입 기록 (1차 + 추매 각각 저장)"""
    price:  float
    usdt:   float
    qty:    float


@dataclass
class PositionState:
    """
    현재 포지션 전체 상태

    position_side 값:
      None              → 미보유
      "CONTRARIAN_SHORT"
      "CONTRARIAN_LONG"
      "TREND_LONG"
    """
    position_side:    Optional[str]   = None
    martingale_level: int             = 0
    entries:          list            = field(default_factory=list)   # list[Entry dict]
    trend_long_stop:  float           = 0.0

    def is_open(self) -> bool:
        return self.position_side is not None

    def avg_price(self) -> float:
        total_qty = sum(e["qty"] for e in self.entries)
        if total_qty == 0:
            return 0.0
        return sum(e["price"] * e["qty"] for e in self.entries) / total_qty

    def total_qty(self) -> float:
        return sum(e["qty"] for e in self.entries)

    def reset(self):
        self.position_side    = None
        self.martingale_level = 0
        self.entries.clear()
        self.trend_long_stop  = 0.0

    def add_entry(self, price: float, usdt: float, qty: float):
        self.entries.append({"price": price, "usdt": usdt, "qty": qty})


def save_state(state: PositionState) -> None:
    """포지션 상태를 JSON 파일로 저장"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(asdict(state), f, indent=2)
    logger.debug(f"[상태저장] {state.position_side} lv={state.martingale_level}")


def load_state() -> PositionState:
    """저장된 상태 복원. 파일 없으면 초기 상태 반환."""
    if not os.path.exists(STATE_FILE):
        return PositionState()
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        state = PositionState(
            position_side    = data.get("position_side"),
            martingale_level = data.get("martingale_level", 0),
            entries          = data.get("entries", []),
            trend_long_stop  = data.get("trend_long_stop", 0.0),
        )
        if state.is_open():
            logger.info(f"[상태복원] {state.position_side} lv={state.martingale_level} "
                        f"진입수={len(state.entries)}")
        return state
    except Exception as e:
        logger.warning(f"[상태복원] 실패 ({e}) → 초기 상태로 시작")
        return PositionState()


def clear_state() -> None:
    """상태 파일 삭제 (포지션 전체 청산 후 호출)"""
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

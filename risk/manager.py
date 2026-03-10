"""
리스크 & 마틴게일 관리
- 차수별 진입 금액 추적
- 평균 단가 계산
- 일일 손실 한도
- 2-2-2 시드 격상 시스템
"""
from typing import Optional
from config.constants import (
    LEVERAGE, MARTINGALE_PCTS, MAX_MARTINGALE_LEVEL,
    MAX_DAILY_LOSS_PCT, INITIAL_CAPITAL,
)


class MartingalePosition:
    """단일 포지션의 마틴게일 상태 추적"""

    def __init__(self, side: str):
        self.side = side                  # "SHORT" / "LONG"
        self.entries: list[dict] = []     # {"price": float, "usdt": float, "qty": float}
        self.level: int = 0

    @property
    def total_usdt(self) -> float:
        return sum(e["usdt"] for e in self.entries)

    @property
    def total_qty(self) -> float:
        return sum(e["qty"] for e in self.entries)

    @property
    def avg_entry_price(self) -> float:
        if self.total_qty == 0:
            return 0.0
        return sum(e["price"] * e["qty"] for e in self.entries) / self.total_qty

    def next_amount(self, capital: float) -> Optional[float]:
        if self.level >= MAX_MARTINGALE_LEVEL:
            return None
        return capital * MARTINGALE_PCTS[self.level]

    def add_entry(self, price: float, usdt_amount: float):
        qty = (usdt_amount * LEVERAGE) / price
        self.entries.append({"price": price, "usdt": usdt_amount, "qty": qty})
        self.level += 1

    def remove_last_entry(self):
        """마지막 차수 물량 덜기 (평단 도달 시)"""
        if self.entries:
            self.entries.pop()
            self.level = max(0, self.level - 1)

    def partial_close(self, ratio: float = 0.5) -> float:
        """
        전체 수량의 ratio만큼 분할 익절
        Returns: 익절된 수량
        """
        close_qty = self.total_qty * ratio
        remaining_ratio = 1.0 - ratio
        for e in self.entries:
            e["qty"] *= remaining_ratio
            e["usdt"] *= remaining_ratio
        return close_qty

    def reset(self):
        self.entries.clear()
        self.level = 0


class RiskManager:
    def __init__(self, capital: float = INITIAL_CAPITAL):
        self.initial_capital = capital
        self.current_capital = capital
        self.daily_start_capital = capital
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.position: Optional[MartingalePosition] = None
        # 2-2-2 격상 시스템
        self.stage_wins = 0             # 현재 시드 체급에서 100% 달성 횟수
        self.backup_capital = 0.0       # 인출된 백업 자금

    def open_position(self, side: str, price: float):
        """1차 진입"""
        self.position = MartingalePosition(side)
        amount = self.current_capital * MARTINGALE_PCTS[0]
        self.position.add_entry(price, amount)

    def add_to_position(self, price: float):
        """추매 (다음 마틴게일 차수)"""
        if self.position is None:
            return
        amount = self.position.next_amount(self.current_capital)
        if amount is None:
            return
        self.position.add_entry(price, amount)

    def close_position(self, exit_price: float) -> float:
        """전량 청산, PnL 반환 (USDT)"""
        if self.position is None:
            return 0.0
        pnl = self._calc_pnl(exit_price, self.position.total_qty, full=True)
        self._record_pnl(pnl)
        self.position.reset()
        self.position = None
        return pnl

    def partial_close_position(self, exit_price: float, ratio: float = 0.5) -> float:
        """분할 익절, PnL 반환"""
        if self.position is None:
            return 0.0
        close_qty = self.position.partial_close(ratio)
        pnl = self._calc_pnl(exit_price, close_qty, full=False)
        self._record_pnl(pnl)
        return pnl

    def _calc_pnl(self, exit_price: float, qty: float, full: bool) -> float:
        if self.position is None:
            return 0.0
        avg_price = self.position.avg_entry_price
        if self.position.side == "LONG":
            raw_pnl = (exit_price - avg_price) * qty
        else:
            raw_pnl = (avg_price - exit_price) * qty
        fee = exit_price * qty * 0.0004
        return raw_pnl - fee

    def _record_pnl(self, pnl: float):
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.current_capital += pnl
        self._check_stage_upgrade()

    def is_daily_loss_exceeded(self) -> bool:
        loss = self.daily_start_capital - self.current_capital
        return loss > self.daily_start_capital * MAX_DAILY_LOSS_PCT

    def reset_daily(self):
        self.daily_start_capital = self.current_capital
        self.daily_pnl = 0.0

    def _check_stage_upgrade(self):
        """2-2-2 법칙: 100% 수익 달성 → 원금 인출 → 2회 성공 시 체급 격상"""
        if self.current_capital >= self.initial_capital * 2:
            self.backup_capital += self.initial_capital
            self.current_capital -= self.initial_capital
            self.stage_wins += 1
            if self.stage_wins >= 2:
                self.initial_capital *= 2
                self.stage_wins = 0

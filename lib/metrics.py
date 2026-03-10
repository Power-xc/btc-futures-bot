"""
공통 메트릭 계산 — 백테스트 전반에서 재사용

calc_metrics() 하나로 PF / MDD / WR / Ret / Score / Kelly 일괄 계산.
pandas 불필요 — 순수 Python, engine·optimize·report 모두에서 import 가능.
"""


def calc_mdd(equity_vals: list) -> float:
    """최대 낙폭(MDD) 계산. equity_vals: [capital, ...]"""
    if not equity_vals:
        return 0.0
    peak = equity_vals[0]
    mdd = 0.0
    for v in equity_vals:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > mdd:
            mdd = dd
    return mdd


def calc_metrics(trades: list, equity_curve: list, initial: float) -> dict:
    """
    핵심 지표 계산 (순수 Python, pandas 불필요)

    Parameters
    ----------
    trades       : engine.run_backtest() 가 반환한 trade dict 리스트
    equity_curve : [(timestamp, capital), ...] 리스트
    initial      : 초기 자본

    Returns
    -------
    dict with keys:
        pf       — Profit Factor
        mdd      — Max Drawdown %
        wr       — Win Rate %
        ret      — Return %
        n        — 총 거래 수
        cap      — 최종 자본
        score    — (PF-1) × (1-MDD/100)  ← 복합 최적화 지표
        avg_win  — 평균 수익 (USDT)
        avg_loss — 평균 손실 (USDT, 양수)
        kelly    — Full Kelly % (베팅 비율 참고용)
    """
    if not trades or not equity_curve:
        return {
            "pf": 0, "mdd": 999, "wr": 0, "ret": -100,
            "n": 0, "cap": initial, "score": -999,
            "avg_win": 0, "avg_loss": 0, "kelly": 0,
        }

    caps = [v for _, v in equity_curve]
    mdd = calc_mdd(caps)

    wins   = [t["pnl_usdt"] for t in trades if t["pnl_usdt"] > 0]
    losses = [t["pnl_usdt"] for t in trades if t["pnl_usdt"] < 0]

    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses)) if losses else 1e-9

    pf  = gross_profit / gross_loss
    wr  = len(wins) / len(trades)
    ret = (caps[-1] - initial) / initial * 100

    avg_win  = gross_profit / len(wins)   if wins   else 0.0
    avg_loss = gross_loss   / len(losses) if losses else 1e-9

    b     = avg_win / avg_loss          # 손익비
    kelly = max(wr - (1 - wr) / b, 0)  # Kelly% = p - q/b

    score = (pf - 1) * (1 - mdd / 100) if mdd < 100 else -999

    return {
        "pf":       round(pf,        3),
        "mdd":      round(mdd,       1),
        "wr":       round(wr * 100,  1),
        "ret":      round(ret,       1),
        "n":        len(trades),
        "cap":      round(caps[-1],  0),
        "score":    round(score,     4),
        "avg_win":  round(avg_win,   3),
        "avg_loss": round(avg_loss,  3),
        "kelly":    round(kelly * 100, 1),
    }

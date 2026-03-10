"""
백테스트 리포트 생성
- 핵심 지표 계산 및 출력
- CSV + 차트 저장
"""
import os
import logging
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime
from tabulate import tabulate

from config.constants import RESULTS_DIR

logger = logging.getLogger(__name__)


def generate_report(trades: list, equity_curve: list,
                    withdrawals: list = None, stage_log: list = None,
                    output_dir: str = None) -> dict:
    if output_dir is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(RESULTS_DIR, f"backtest_{ts}")
    os.makedirs(output_dir, exist_ok=True)

    if not trades:
        logger.warning("거래 없음 - 전략 파라미터 확인 필요")
        return {}

    df = pd.DataFrame(trades)
    initial = equity_curve[0][1]
    final = equity_curve[-1][1]

    # 기본 지표
    wins = df[df["pnl_usdt"] > 0]
    losses = df[df["pnl_usdt"] <= 0]
    win_rate = len(wins) / len(df) * 100 if len(df) > 0 else 0
    avg_win = wins["pnl_usdt"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl_usdt"].mean() if len(losses) > 0 else 0
    profit_factor = (wins["pnl_usdt"].sum() / abs(losses["pnl_usdt"].sum())
                     if len(losses) > 0 and losses["pnl_usdt"].sum() != 0 else float("inf"))

    # MDD
    eq_vals = [v for _, v in equity_curve]
    peak = eq_vals[0]
    max_dd = 0.0
    for v in eq_vals:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100
        max_dd = max(max_dd, dd)

    # 방향별 통계
    long_trades = df[df["side"].isin(["CONTRARIAN_LONG", "TREND_LONG"])]
    short_trades = df[df["side"] == "CONTRARIAN_SHORT"]
    trend_trades = df[df["side"] == "TREND_LONG"]

    # 출금 통계
    total_withdrawn = sum(w["withdrawn"] for w in (withdrawals or []))
    withdrawal_count = len(withdrawals or [])

    # 청산 사유별
    reason_counts = df["reason"].value_counts().to_dict()

    metrics = {
        "initial": initial, "final": final,
        "net_pnl": final - initial,
        "total_return_pct": (final - initial) / initial * 100,
        "total_trades": len(df),
        "wins": len(wins), "losses": len(losses),
        "win_rate": win_rate,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "trend_trades": len(trend_trades),
        "long_pnl": long_trades["pnl_usdt"].sum() if len(long_trades) > 0 else 0,
        "short_pnl": short_trades["pnl_usdt"].sum() if len(short_trades) > 0 else 0,
        "trend_pnl": trend_trades["pnl_usdt"].sum() if len(trend_trades) > 0 else 0,
        "total_withdrawn": total_withdrawn,
        "withdrawal_count": withdrawal_count,
        "total_value": final + total_withdrawn,
        "reason_counts": reason_counts,
        "stage_log": stage_log or [],
    }

    _print_summary(metrics)
    _save_trades_csv(df, output_dir)
    if withdrawals:
        _save_withdrawal_csv(withdrawals, output_dir)
    _save_equity_chart(equity_curve, output_dir)
    _save_monthly_chart(df, output_dir)

    logger.info(f"리포트 저장: {output_dir}")
    return metrics


def _print_summary(m: dict):
    pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float("inf") else "∞"
    rows = [
        ["초기 자본",        f"${m['initial']:,.2f}"],
        ["최종 자본 (잔여)",  f"${m['final']:,.2f}"],
        ["총 출금",          f"${m['total_withdrawn']:,.2f} ({m['withdrawal_count']}회)"],
        ["총 자산 (잔여+출금)", f"${m['total_value']:,.2f}"],
        ["총 수익률",        f"{(m['total_value']-m['initial'])/m['initial']*100:+.2f}%"],
        ["", ""],
        ["총 거래",          f"{m['total_trades']}회"],
        ["  역추세 롱",      f"{m['long_trades'] - m.get('trend_trades',0)}회 (${m['long_pnl']-m.get('trend_pnl',0):+.2f})"],
        ["  추세 롱",        f"{m.get('trend_trades',0)}회 (${m.get('trend_pnl',0):+.2f})"],
        ["  역추세 숏",      f"{m['short_trades']}회 (${m['short_pnl']:+.2f})"],
        ["승률",             f"{m['win_rate']:.1f}%"],
        ["", ""],
        ["평균 수익",        f"${m['avg_win']:+.2f}"],
        ["평균 손실",        f"${m['avg_loss']:+.2f}"],
        ["수익인수 (PF)",    pf_str],
        ["최대 낙폭 (MDD)",  f"{m['max_drawdown']:.2f}%"],
        ["", ""],
        ["[청산 사유]", ""],
    ]
    for reason, count in m.get("reason_counts", {}).items():
        rows.append([f"  {reason}", f"{count}회"])

    if m.get("stage_log"):
        rows.append(["", ""])
        rows.append(["[체급 격상 이력]", ""])
        for s in m["stage_log"]:
            rows.append([f"  {s['time']}", f"새 시드 ${s['new_stage']:,.0f}"])

    print("\n" + "=" * 60)
    print("         백테스트 결과 요약")
    print("=" * 60)
    print(tabulate(rows, tablefmt="plain"))
    print("=" * 60 + "\n")

    # 전략 평가
    pf = m["profit_factor"]
    wr = m["win_rate"]
    mdd = m["max_drawdown"]
    if pf >= 1.5 and wr >= 45 and mdd <= 20:
        print("[전략 평가] 우수 → 라이브 테스트 고려 가능\n")
    elif pf >= 1.2 and wr >= 40:
        print("[전략 평가] 보통 → 파라미터 조정 후 재테스트 권장\n")
    else:
        print("[전략 평가] 미달 → 전략 개선 필요\n")


def _save_trades_csv(df: pd.DataFrame, output_dir: str):
    path = os.path.join(output_dir, "trades.csv")
    df.to_csv(path, index=False)
    logger.info(f"거래 내역: {path}")


def _save_withdrawal_csv(withdrawals: list, output_dir: str):
    path = os.path.join(output_dir, "withdrawals.csv")
    pd.DataFrame(withdrawals).to_csv(path, index=False)
    logger.info(f"출금 내역: {path}")


def _save_equity_chart(equity_curve: list, output_dir: str):
    timestamps = [datetime.fromtimestamp(ts / 1000) for ts, _ in equity_curve]
    values = [v for _, v in equity_curve]
    initial = values[0]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(timestamps, values, color="#00bcd4", linewidth=1.2)
    ax.fill_between(timestamps, values, initial,
                    where=[v >= initial for v in values], alpha=0.3, color="#4caf50")
    ax.fill_between(timestamps, values, initial,
                    where=[v < initial for v in values], alpha=0.3, color="#f44336")
    ax.axhline(initial, color="#888", linestyle="--", linewidth=0.8)
    ax.set_title("Equity Curve")
    ax.set_ylabel("Capital (USDT)")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    path = os.path.join(output_dir, "equity_curve.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    logger.info(f"에쿼티 차트: {path}")


def _save_monthly_chart(df: pd.DataFrame, output_dir: str):
    df = df.copy()
    df["month"] = pd.to_datetime(df["close_time"]).dt.to_period("M").astype(str)
    monthly = df.groupby("month")["pnl_usdt"].sum()

    fig, ax = plt.subplots(figsize=(12, 4))
    colors = ["#4caf50" if v >= 0 else "#f44336" for v in monthly.values]
    ax.bar(monthly.index, monthly.values, color=colors, alpha=0.8)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_title("Monthly PnL (USDT)")
    ax.set_ylabel("PnL (USDT)")
    plt.xticks(rotation=45)
    fig.tight_layout()
    path = os.path.join(output_dir, "monthly_pnl.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    logger.info(f"월별 차트: {path}")

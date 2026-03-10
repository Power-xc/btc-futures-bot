# =============================================================
# 전략 파라미터 설정
# =============================================================
# 최적화 이력: 7년(2018-2025) 734,806개 캔들 기반 민감도 분석
# 목표: PF 최대화 + MDD 최소화 (복합 스코어: (PF-1)×(1-MDD/100))
#
# ★ 2차 최적화 (전체 파라미터 조합 탐색):
#   기존: VOL_WEAK=0.70  VOL_TREND=3.00  → PF=1.584  MDD=51.8%  Ret=+60.8%  WR=61.1%
#   신규: VOL_WEAK=0.92  VOL_TREND=3.50  → PF=1.877  MDD=49.9%  Ret=+244.5% WR=66.7%
#   개선: 수익 4배↑  MDD 1.9%↓  WR 5.6%↑  전 연도 흑자
# =============================================================

SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"

# --- 거래량 절대 기준 (BTC) — 폴백용 (vol_avg 없을 때만 사용) ---
VOLUME_STRONG_BTC = 3000
VOLUME_TREND_BTC  = 1000
VOLUME_WEAK_BTC   = 500

# --- 거래량 상대 기준 (★ 핵심 파라미터 — 시대·시장 무관) ---
# 최근 20봉 평균 대비 상대 비율로 판단 → 2018/2022/2024 어느 시대도 동일하게 작동
#
# 1차 민감도 분석 (BODY=0.8% 기준, 7년):
#   VOL_WEAK_RATIO  0.50 → PF=1.127  MDD=84.1%   score=0.075
#   VOL_WEAK_RATIO  0.70 → PF=1.584  MDD=51.8%   score=0.281 (1차 채택)
#   VOL_WEAK_RATIO  0.90 → PF=1.012  MDD=95.2%   score=0.001  ← BODY=0.8% 기준
#
# 2차 조합 탐색 (BODY=1.0% 적용 후, 전년도 흑자 조건):
#   VOL_WEAK_RATIO  0.92  VOL_TREND_RATIO 3.00 → score=0.3828
#   VOL_WEAK_RATIO  0.92  VOL_TREND_RATIO 3.50 → score=0.4398 ★ (채택)
#   VOL_WEAK_RATIO  0.90  VOL_TREND_RATIO 2.50 → score=0.3879
#
# (indicators.py에 VOL_WEAK_RATIO, VOL_TREND_RATIO, VOL_STRONG_RATIO 로 정의)

# --- 가짜 움직임 감지 (역추세 진입 신호) ---
# 수학적 최적값: 7년 민감도 분석
#   BODY=0.5% → PF=1.100  MDD=125.3%  (과진입, 전액 손실 위험)
#   BODY=0.6% → PF=1.194  MDD=109.4%  (과진입)
#   BODY=0.8% → PF=1.224  MDD= 70.6%  (이전 기본값)
#   BODY=1.0% → PF=1.584  MDD= 51.8%  score=0.281 ★ (채택)
#   BODY=1.2% → PF=1.442  MDD= 49.9%  (거래 수 부족, 통계 불안정)
FAKE_MOVE_BODY_PCT   = 0.010     # 캔들 몸통 1.0% 이상 (수학적 최적값)
FAKE_MOVE_BODY_RATIO = 0.65      # 몸통/전체범위 65% 이상 (꼬리 짧아야)

# --- 피뢰침 감지 (추매 / 분할익절 트리거) ---
# 수학적 최적값: 7년 민감도 분석
#   SPIKE=1.0% → PF=1.334  MDD=85.0%   score=0.030  (MDD 급등)
#   SPIKE=1.2% → PF=1.373  MDD=47.0%   score=0.198
#   SPIKE=1.5% → PF=1.584  MDD=51.8%   score=0.281 ★ (채택 — WEAK=0.92 조합에서도 최적)
#   SPIKE=2.0% → PF=1.336  MDD=50.8%   score=0.165
SPIKE_BODY_PCT          = 0.005  # 단일 캔들 몸통 최소 0.5%
SPIKE_WICK_MIN_RATIO    = 0.50   # 단일 캔들 꼬리 50% 이상
SPIKE_CLUSTER_MOVE_PCT  = 0.015  # 클러스터(2-3 캔들) 전체 이동 최소 1.5%

# --- VOL_AVG_WINDOW 민감도 분석 결과 ---
# (engine.py 내 vol_avg_window 파라미터)
#   WIN= 5봉 → PF=1.155  MDD= 88.3%   (노이즈 과다)
#   WIN=10봉 → PF=1.142  MDD= 79.3%   (불안정)
#   WIN=20봉 → PF=1.584  MDD= 51.8%   score=0.281 ★ (채택 — WEAK=0.92 조합에서도 최적)
#   WIN=30봉 → PF=0.132  MDD=103.9%   (기준선 왜곡 → 파산)
# → engine.py vol_avg_window 기본값 = 20 (변경 금지)

# --- 하락 거래량 무시: 음봉은 캔들 구조로만 판단 ---
STRONG_BEARISH_BODY_PCT = 0.012  # 강한 음봉 몸통 1.2%

# --- 계단식 움직임 감지 (홀딩 유지) ---
STAIRCASE_LOOKBACK    = 5
STAIRCASE_MAX_BODY_PCT = 0.003
STAIRCASE_MIN_COUNT   = 3

# --- 거래량 소멸 감지 (완익 신호) ---
VOL_EXHAUST_LOOKBACK  = 4
VOL_EXHAUST_DROP_RATIO = 0.30

# --- 추세 롱 전략 ---
TREND_CONTINUATION_BTC  = 1500
TREND_REVERSAL_BTC      = 3000
TREND_LONG_MIN_STOP_PCT = 0.005   # 손절가 최소 거리 0.5% (진입가 대비)

# --- 레버리지 & 마틴게일 ---
# 사이징 최적화 결과 (7년 검증):
#   $20×2.0배수 = [20, 40, 80, 160, 320]  → 출금포함 $5,646  score=0.333 (구 기준)
#   $15×2.5배수 = [15, 38, 95, 238, 595]  → 출금포함 $8,729  score=0.499 ★ (채택)
#   $20×2.5배수 = [20, 50, 125, 312, 780] → 출금포함 $10,671 score=0.416 (MDD↑)
#   $25×2.5배수 = [25, 62, 155, 388, 970] → 출금포함 $11,142 score=0.294 (MDD↑↑)
LEVERAGE = 20
MARTINGALE_AMOUNTS = [15, 38, 95, 238, 595]   # ×2.5배수 (수학적 최적값)
MAX_MARTINGALE_LEVEL = 5

# --- 리스크 관리 ---
MAX_DAILY_LOSS_PCT = 0.10
INITIAL_CAPITAL    = 1000

# --- 2-2-2 시드 격상 시스템 ---
STAGE_UP_MULTIPLIER = 2.0
STAGE_UP_WIN_COUNT  = 2

# --- 백테스팅 ---
BACKTEST_TAKER_FEE       = 0.0004
BACKTEST_SLIPPAGE        = 0.0002
BACKTEST_MIN_CANDLES     = 25
BACKTEST_WINDOW_SIZE     = 50
PARTIAL_CLOSE_RATIO      = 0.5
MAX_ENTRY_CAPITAL_RATIO  = 0.95

# --- 경로 ---
SPOT_BASE_URL    = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"
DATA_DIR         = "data/historical"
RESULTS_DIR      = "results"
LOGS_DIR         = "logs"

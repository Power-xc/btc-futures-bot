# BTC 선물 자동매매 봇

BTC/USDT 5분봉 기반 역추세 + 추세 롱 전략. 7년(2018–2025) 백테스트 최적화 완료.

---

## 전략 요약

| 항목 | 내용 |
|------|------|
| 심볼 | BTCUSDT 선물 |
| 봉 단위 | 5분봉 |
| 전략 | 역추세 숏/롱(가짜 거래량 감지) + 추세 롱(3.5x 거래량) |
| 마틴게일 | 잔고의 1% → 2.5% → 6.3% → 15.8% → 39.4% (×2.5배수, 합계 65%, 복리) |
| 레버리지 | 20x |
| 리스크 관리 | 2-2-2 출금 시스템 (자본 2배 시 원금 출금) |

### 7년 백테스트 성과 (2018–2025, 초기 $1,000)

| 지표 | 수치 |
|------|------|
| Profit Factor | **1.921** |
| 승률 (WR) | **66.8%** |
| 최대 낙폭 (MDD) | 59.7% |
| 출금 포함 총 자산 | **$11,573** |
| 연도별 손실 | 2019년만 소폭 손실, 나머지 6년 전부 흑자 |

---

## 폴더 구조

```
btc-futures-bot/
├── backtest/              # 백테스트 엔진
│   ├── engine.py          # 핵심 백테스트 루프 (마틴게일 + 2-2-2 출금)
│   ├── data_loader.py     # Binance API 데이터 로드 + CSV 캐시
│   └── report.py          # 결과 리포트 + 차트 생성
├── config/
│   ├── constants.py       # ★ 모든 전략 파라미터 (여기서만 수정)
│   └── settings.py        # API 키 등 환경 설정
├── lib/
│   ├── metrics.py         # PF/MDD/WR/Score/Kelly 계산 (공통)
│   └── volume.py          # vol_avg 슬라이딩 윈도우 계산 (공통)
├── strategy/
│   ├── indicators.py      # 거래량 판단 함수 (VOL_WEAK/TREND/STRONG)
│   ├── patterns.py        # 캔들 패턴 감지 (fake pump/dump, spike, staircase)
│   └── signals.py         # 시그널 상태머신 (IDLE → ENTER/ADD/CLOSE)
├── scripts/               # 분석/최적화 스크립트 (운영과 분리)
│   ├── optimize.py        # 파라미터 민감도 분석
│   ├── optimize_sizing.py # 레버리지/마틴게일/Kelly 최적화
│   └── test_3tick.py      # 3틱룰 단타 테스트 (아카이브)
├── data/historical/       # Binance 캔들 CSV 캐시
├── results/               # 백테스트 결과 (CSV + 차트)
├── core/
│   ├── trader.py          # 실시간 트레이딩 루프 (5분봉 폴링)
│   └── state.py           # 포지션 상태 JSON 저장/복원
├── exchange/
│   ├── client.py          # ccxt Binance 클라이언트 (testnet 지원)
│   └── order.py           # 주문 실행 (비율 기반 마틴게일)
├── notifications/
│   └── telegram.py        # 텔레그램 알림 (진입/청산/에러)
├── logs/                  # 로그 파일
├── run_backtest.py        # ★ 백테스트 실행 진입점
└── run_live.py            # ★ 실거래 실행 진입점 (--dry-run 지원)
```

---

## 빠른 시작

### 1. 환경 설정

```bash
pip install -r requirements.txt
```

### 2. 백테스트 실행

```bash
# 기본 (2022–2025, 3년)
python run_backtest.py

# 기간 지정
python run_backtest.py --start 2020-01-01 --end 2025-01-01

# 초기 자본 변경
python run_backtest.py --capital 500

# 캐시 무시하고 새로 다운로드
python run_backtest.py --no-cache

# 상세 로그
python run_backtest.py --verbose
```

결과는 `results/backtest_YYYYMMDD_HHMMSS/` 폴더에 저장됩니다.

### 3. 실거래 실행

```bash
# .env 파일 생성 (.env.example 참고)
cp .env.example .env

# 드라이런 (주문 없이 시그널만 확인 — 먼저 실행 권장)
python run_live.py --dry-run

# 실거래
python run_live.py
```

---

## 파라미터 설명 (`config/constants.py`)

### 거래량 상대 기준 (★ 가장 중요)
```python
VOL_WEAK_RATIO   = 0.92   # 평균의 92% 미만 → 가짜 움직임 (역추세 진입)
VOL_TREND_RATIO  = 3.50   # 평균의 350% 이상 (3.5x) → 진짜 추세 (추세 롱)
```
최근 20봉 평균 대비 상대 비율 → 2018년 저유동성 ~ 2024년 고유동성 모두 동일 기준 적용.

### 역추세 진입 필터
```python
FAKE_MOVE_BODY_PCT   = 0.010   # 캔들 몸통 최소 1.0%
FAKE_MOVE_BODY_RATIO = 0.65    # 몸통/전체범위 65% 이상
```

### 마틴게일 & 레버리지
```python
LEVERAGE          = 20
MARTINGALE_PCTS   = [0.01009, 0.02523, 0.06307, 0.15768, 0.39420]  # 합계 ≈ 65% (현재 자본 기준 복리)
MAX_MARTINGALE_LEVEL = 5
# 예) 잔고 $1,000: $10 → $25 → $63 → $158 → $394
# 예) 잔고 $2,000: $20 → $50 → $126 → $315 → $788  (체급 격상 시 자동 2배)
```

### 2-2-2 출금 시스템
```python
STAGE_UP_MULTIPLIER = 2.0   # 자본 2배 되면 원금 출금
```

---

## 전략 로직

### 역추세 전략 (주전략)
```
양봉 + 거래량 미달(< 평균 92%) + 몸통 ≥ 1% → 숏 진입  (가짜 펌프 페이드)
음봉 + 거래량 미달(< 평균 92%) + 몸통 ≥ 1% → 롱 진입  (가짜 덤프 페이드)
```

### 추세 롱 전략 (보조전략)
```
양봉 + 거래량 3.5x 이상 + 몸통 ≥ 1% → 롱 진입 (진짜 기관 매수세)
손절: 신호 캔들 2봉 전 저점 (최소 진입가 대비 -0.5%)
익절: 역방향 3.5x 거래량 캔들
```

### 마틴게일 추매
```
진입 후 역방향 피뢰침 → 다음 레벨 추매
최대 5레벨: 잔고 × [1% → 2.5% → 6.3% → 15.8% → 39.4%]
합계 ≈ 65% (체급 격상 시 베팅 자동 2배 — 복리)
```

### 2-2-2 출금
```
자본 2배 달성 → 원금 출금 → 2회 반복 → 시드 체급 2배 격상
```

---

## 분석 스크립트

```bash
# 파라미터 민감도 분석 (~12분)
python scripts/optimize.py

# 레버리지/마틴게일/Kelly 최적화 (~30분)
python scripts/optimize_sizing.py
```

---

## 주의사항

- 백테스트 과거 데이터 기반 — 미래 수익 보장 없음
- MDD 59.7% → 실제 운용 시 정신적 내성 필요
- 마틴게일 5레벨 최대 노출: 잔고의 65% (복리 — 체급 격상 시 자동 2배)
- **권장 최소 자본: $1,000 이상**

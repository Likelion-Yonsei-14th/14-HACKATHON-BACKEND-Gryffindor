# Backend Server

스마트글래스 기반 관광객 쇼핑 지원 서비스의 백엔드 서버다.

이 저장소는 **모바일 앱이 사용자 경험과 카메라 처리를 담당하고, 백엔드는 제품 식별·가격 정보·쇼핑 이력·출국 단계 로직을 제공하는 구조**를 전제로 한다.

## MVP 목표

스마트글래스를 착용한 관광객이 매장에서 관심 있게 본 상품을 모바일 앱이 감지하고, 백엔드가 해당 상품을 식별해 다음 정보를 반환한다.

- 상품명 / 이미지
- 국내 정가
- 예상 환급 적용가
- 자국 통화 환산가
- 즉시환급 가능 여부

쇼핑 종료 후에는 사용자가 구매 상품과 관심 상품을 구분하고, 출국 공항·항공편·공항 도착 예정 시간을 입력한다. 백엔드는 이를 바탕으로 환급 체크리스트와 공항 기준 추천 결과를 제공한다.

## 전체 흐름

```text
Meta Gen2
  ↓
Android App
  ├─ Camera Stream
  ├─ Object Detection / Tracking
  ├─ 중앙 시야 + 화면 점유율 + 지속 시간 판정
  └─ 관심 조건 만족 프레임 crop
        ↓ HTTPS
FastAPI Backend
  ├─ OpenAI Vision 기반 상품 식별
  ├─ Product Catalog
  ├─ Pricing / Refund / FX
  ├─ Shopping Session
  ├─ Purchase / Interest Review
  ├─ Refund Checklist
  └─ Airport Recommendation
        ↓
PostgreSQL
```

## 핵심 원칙

1. **별도 Web Frontend를 만들지 않는다.** Android 앱이 유일한 사용자 UI다.
2. **카메라 스트림·Bounding Box·관심 행동 판정은 앱 책임이다.** 서버는 영상 스트림을 계속 받지 않는다.
3. **OpenAI API Key는 서버에만 존재한다.** 앱에 API Key를 포함하지 않는다.
4. Recognition은 OpenCLIP/pgvector가 아니라 **OpenAI image input + structured output**을 사용한다.
5. UI 팀과 병렬 작업할 수 있도록 **API DTO를 먼저 고정하고 Mock/Real Provider를 같은 인터페이스로 교체**한다.
6. 정확한 세금 환급 규칙·실시간 환율·공항 상품 데이터는 외부 의존성이므로 Provider로 분리한다.

## 문서 읽는 순서

1. `docs/REQUIREMENTS.md`
2. `docs/ARCHITECTURE.md`
3. `docs/API_CONTRACT.md`
4. `docs/DATA_MODEL.md`
5. `docs/RECOGNITION.md`
6. `docs/DEVELOPMENT_PLAN.md`
7. `docs/APP_INTEGRATION.md`
8. `docs/TEST_PLAN.md`

## MVP에서 제외

- Web UI / SSE
- OpenCLIP / PyTorch / pgvector
- 결제 처리
- 실제 세금 환급 신청
- Eye Tracking
- Hand Tracking 기반 "제품을 들었음" 판정
- 실시간 공항 면세점 재고 보장
- 로그인 / 회원가입
- 고도화된 추천 모델

## Backend 개발 환경

필수 도구:

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop 또는 Docker Engine + Compose

PostgreSQL을 시작한다. 로컬의 일반 PostgreSQL과 충돌하지 않도록 기본 호스트 포트는
`55433`을 사용한다. `POSTGRES_PORT`로 변경할 경우 `backend/.env`의 `DATABASE_URL`
포트도 같은 값으로 맞춘다.

```bash
docker compose up -d --wait postgres
```

백엔드 전용 가상환경을 만들고 lock된 의존성을 설치한다.

```bash
cd backend
uv venv .venv --python 3.11
uv sync --locked
```

필요하면 `backend/.env.example`을 `backend/.env`로 복사한 뒤, migration과 서버를
실행한다. 모든 Python 명령은 `backend/.venv`를 사용한다.

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.seed_products
.venv/bin/uvicorn app.main:app --reload
```

- Health: `http://127.0.0.1:8000/health`
- Swagger UI: `http://127.0.0.1:8000/docs`

## B1 Mock Vertical Slice

기본 `MOCK_RECOGNITION_STATUS=MATCHED`에서는 업로드된 유효한 JPEG/PNG crop을
`MOCK_RECOGNITION_PRODUCT_ID` 상품으로 인식한다. Android의 상태별 UI를 검증할 때는
`backend/.env`에서 `MOCK_RECOGNITION_STATUS`를 `AMBIGUOUS` 또는 `UNKNOWN`으로 바꾸고
서버를 재시작한다. 이 모드에서는 OpenAI API를 호출하지 않는다.

구현된 API:

- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{sessionId}/recognize`
- `GET /api/v1/sessions/{sessionId}/products`
- `POST /api/v1/sessions/{sessionId}/complete`

검증 명령:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
```

## B2 OpenAI Recognition

기본값은 계속 `RECOGNITION_PROVIDER=mock`이므로 일반 개발과 pytest에서는 OpenAI를
호출하지 않는다. 실제 Provider를 사용할 때만 `backend/.env`에 다음 값을 설정한다.

```bash
RECOGNITION_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_VISION_MODEL=gpt-5-mini
OPENAI_TIMEOUT_SECONDS=20
RECOGNITION_MAX_CANDIDATES=20
```

실제 API smoke test도 opt-in이다. Catalog 상품 crop과 기대 결과를 명시한 경우에만
아래처럼 실행한다.

```bash
RUN_OPENAI_RECOGNITION_SMOKE=1 \
OPENAI_RECOGNITION_SMOKE_IMAGE=/absolute/path/to/crop.jpg \
OPENAI_RECOGNITION_SMOKE_EXPECTED_STATUS=MATCHED \
OPENAI_RECOGNITION_SMOKE_EXPECTED_PRODUCT_ID=mcm_001 \
.venv/bin/python -m pytest -m openai_smoke
```

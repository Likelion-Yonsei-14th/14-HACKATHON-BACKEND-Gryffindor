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

실제 API 흐름은 seed된 `Product.image_url`을 reference image URL로 사용한다.
Catalog을 DB에 반영하려면 다음 seed command를 실행한다.

```bash
cd backend
.venv/bin/python -m app.scripts.seed_products
```

OpenAI smoke test는 DB를 사용하지 않고 `data/products.seed.json`과 아래 local fixture를
직접 읽는 opt-in test다. Fixture JPEG은 촬영 원본의 EXIF를 제거하고 긴 변을 최대
1024px로 줄여 둔다.

```text
backend/tests/fixtures/openai/
├─ demo_lotion_001_ref.jpg
├─ demo_mouse_001_ref.jpg
├─ demo_perfume_001_ref.jpg
└─ query/
   ├─ demo_lotion_001_query.jpg
   ├─ demo_mouse_001_query.jpg
   ├─ demo_perfume_001_query.jpg
   └─ unrelated.jpg
```

각 `*_query.jpg`는 같은 상품의 `*_ref.jpg`와 다른 각도에서 촬영한 이미지여야 한다.
`unrelated.jpg`는 Catalog 상품과 무관한 JPEG이어야 한다. A4 상품 3개의 MATCHED만 먼저
검증할 때는 다음처럼 실제 OpenAI 호출을 명시적으로 opt-in한다.

```bash
cd backend
RUN_OPENAI_RECOGNITION_SMOKE=1 \
.venv/bin/python -m pytest tests/test_openai_recognition_smoke.py \
  -k a4_demo_catalog -v
```

### A4 Demo Recognition Catalog

기존 mock 상품은 유지하고 다음 세 상품을 `data/products.seed.json`에 추가한다.

```text
demo_lotion_001   BRINGGREEN 티트리 시카 수딩 크림 100ml
demo_mouse_001    Logitech M185 무선 마우스 (그레이)
demo_perfume_001  Diptyque 로 파피에 오 드 뚜왈렛 100ml
```

Seed는 `productId` 기준 upsert이므로 기존 DB를 지우지 않고 반복 실행할 수 있다.

```bash
cd backend
.venv/bin/python -m app.scripts.seed_products
```

실제 `/recognize` E2E에서는 DB의 `Product.image_url`을 OpenAI reference image URL로
사용한다. A4에서는 HTTPS로 접근 가능한 JPEG URL을 seed에 넣었으며, Real Provider 실행
시 정렬상 앞의 demo 상품 3개만 allowlist로 사용하도록 `backend/.env`를 설정한다.

```bash
RECOGNITION_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_VISION_MODEL=gpt-5-mini
OPENAI_TIMEOUT_SECONDS=20
RECOGNITION_MAX_CANDIDATES=3
```

DB 반영 결과는 다음 명령으로 확인한다.

```bash
docker compose exec postgres psql -U postgres -d gryffindor \
  -c "SELECT product_id, brand, name FROM products WHERE product_id LIKE 'demo_%' ORDER BY product_id;"
```

## B3 Android 실기기 연결

기본 실행 명령은 개발 PC의 localhost에만 bind된다. Android 실기기와 개발 PC를 같은
신뢰된 LAN에 연결한 뒤, 실기기 테스트가 필요할 때만 다음처럼 LAN interface에서도
요청을 받는다.

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`0.0.0.0`은 서버의 listen 주소이며 Android Base URL로 사용할 수 없다. Android 개발
build의 `API_BASE_URL`에는 개발 PC의 실제 LAN IP를 넣고 Retrofit에서 사용할 수 있도록
마지막 `/`를 유지한다.

```text
API_BASE_URL=http://<개발-PC-LAN-IP>:8000/
```

실기기에서 먼저 다음 두 요청을 확인한다.

```text
GET  http://<개발-PC-LAN-IP>:8000/health
POST http://<개발-PC-LAN-IP>:8000/api/v1/sessions
Content-Type: application/json

{"currency":"CNY"}
```

Health는 `200 {"status":"ok"}`, Session 생성은 `201`과 `sessionId`를 반환해야 한다.
Native Android Retrofit/OkHttp 요청에는 CORS 설정이 필요하지 않다. 개발 build에서 HTTP를
사용한다면 Android의 cleartext 허용도 개발 환경에만 한정하고, 배포 환경은 HTTPS Base
URL을 사용한다.

이 bind 방식은 신뢰된 개발 LAN에서만 사용한다. 라우터 port forwarding을 설정하거나
방화벽을 무조건 개방해 인터넷에 직접 노출하지 않는다. 외부 네트워크에서 검증해야 한다면
인증서와 접근 제어가 적용된 기존 HTTPS 배포 주소를 사용한다.

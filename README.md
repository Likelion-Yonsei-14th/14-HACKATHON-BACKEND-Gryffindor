# Gryffindor Backend

Meta Ray-Ban Gen 2 쇼핑 지원 Android 앱의 FastAPI 백엔드다.

## 현재 시연 경로

```text
Android DAT camera
→ on-device detection / attention gate
→ product crop
→ OpenCLIP embedding
→ pgvector catalog match
→ product / pricing / session response
```

기본 인식 Provider는 `openclip`이다. 기본 경로에서는 OpenAI API를 호출하지 않으며 threshold를 통과하지 못한 이미지는 `UNKNOWN`으로 반환한다.

## 필수 도구

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop 또는 Docker Engine + Compose

## 최초 1회 설정

저장소 루트에서 pgvector PostgreSQL을 시작한다.

```bash
docker compose up -d --wait postgres
```

Python 환경과 lock된 의존성을 설치한다. 최초 설치 시 OpenCLIP model weight 다운로드가 발생할 수 있다.

```bash
cd backend
uv sync --locked --python 3.11
```

`backend/.env`가 없을 때만 example을 복사한다.

```bash
cp .env.example .env
```

기본 설정은 다음과 같다. 다른 Provider 선택지는 주석으로 보존한다.

```text
RECOGNITION_PROVIDER=openclip
# RECOGNITION_PROVIDER=openai
# RECOGNITION_PROVIDER=mock

RECOGNITION_MAX_CANDIDATES=3
OPENCLIP_MATCH_THRESHOLD=0.62
OPENCLIP_MARGIN_THRESHOLD=0.06
```

DB schema, demo catalog, reference embedding을 준비한다.

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.seed_products
.venv/bin/python -m app.scripts.index_product_embeddings
```

Embedding index command는 로컬 `tests/fixtures/openai/`의 `demo_*_ref.jpg` 파일을 사용한다. Catalog나 reference image를 바꾸면 다시 실행한다.

## 서버 실행

Android 실기기에서 접근할 수 있도록 LAN에 bind한다.

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

시연 중에는 `--reload`를 붙이지 않는다.

- Health: `http://127.0.0.1:8000/health`
- Swagger: `http://127.0.0.1:8000/docs`
- Android base URL: `http://<개발-PC-LAN-IP>:8000/api/v1/`
- 현재 테스트 LAN: `http://172.30.1.4:8000/api/v1/`

LAN IP가 바뀌면 Android `BACKEND_BASE_URL`도 변경한다. `0.0.0.0`은 bind 주소이므로 Android URL로 쓰지 않는다.

## 빠른 상태 확인

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"currency":"KRW"}'
```

정상 결과는 health `200`, session 생성 `201`이다.

## Provider 전환

기본 OpenCLIP:

```text
RECOGNITION_PROVIDER=openclip
```

OpenAI를 명시적으로 사용할 때만 `.env`의 OpenAI 항목 주석을 해제하고 API key를 설정한다.

```text
RECOGNITION_PROVIDER=openai
OPENAI_API_KEY=<your-key>
OPENAI_VISION_MODEL=gpt-5.6-luna
```

Android UI 상태만 검증할 때는 Mock을 사용한다.

```text
RECOGNITION_PROVIDER=mock
```

## 테스트

일반 테스트는 로컬 `.env`와 격리되어 Mock/Fake Provider만 사용한다.

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
```

## 핵심 API

- `GET /health`
- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{sessionId}/recognize`
- `GET /api/v1/sessions/{sessionId}/products`
- `POST /api/v1/sessions/{sessionId}/complete`

나머지 DTO와 endpoint는 [API contract](docs/API_CONTRACT.md)를 따른다.

## 문서

1. [Requirements](docs/REQUIREMENTS.md)
2. [Architecture](docs/ARCHITECTURE.md)
3. [API contract](docs/API_CONTRACT.md)
4. [Recognition](docs/RECOGNITION.md)
5. [Android integration](docs/APP_INTEGRATION.md)

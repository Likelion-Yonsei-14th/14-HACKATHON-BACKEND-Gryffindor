# Gryffindor Backend

Meta Ray-Ban Gen 2 쇼핑 지원 Android 앱의 FastAPI 백엔드다.

## 책임 범위

```text
Android: DAT camera → on-device detection/attention → product crop
Backend: crop → OpenAI recognition → catalog/pricing/session response
```

백엔드는 카메라 스트림, object detection, attention gate를 처리하지 않는다. 별도 Web UI도 없다.

## 필수 도구

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop 또는 Docker Engine + Compose
- OpenAI API key

## 최초 1회 설정

저장소 루트에서 PostgreSQL을 시작한다.

```bash
docker compose up -d --wait postgres
```

백엔드 환경과 의존성을 준비한다.

```bash
cd backend
uv sync --locked --python 3.11
cp .env.example .env
```

기존 `backend/.env`가 있다면 덮어쓰지 않는다. 다음 값만 확인하고 API key는 저장소에 커밋하지 않는다.

```text
RECOGNITION_PROVIDER=openai
OPENAI_API_KEY=<your-key>
OPENAI_VISION_MODEL=gpt-5.6-luna
RECOGNITION_MAX_CANDIDATES=3
```

OpenAI API key는 서버 환경변수에서만 읽고 Android 앱에는 넣지 않는다. 현재 모델은 이미지 입력을 지원하는 `gpt-5.6-luna`이며 필요하면 환경변수로 교체한다.

DB schema와 demo catalog를 준비한다.

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.seed_products
```

## 서버 실행

Android 실기기에서 접근할 수 있도록 LAN에 bind한다.

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

개발 중 자동 재시작이 필요할 때만 `--reload`를 추가한다. 시연 중에는 프로세스 중복과 모델 재로딩을 피하기 위해 사용하지 않는다.

- Health: `http://127.0.0.1:8000/health`
- Swagger: `http://127.0.0.1:8000/docs`
- Android API base URL: `http://<개발-PC-LAN-IP>:8000/api/v1/`

현재 테스트 LAN에서 Android 앱은 다음 주소를 사용한다.

```text
http://172.30.1.4:8000/api/v1/
```

LAN IP가 바뀌면 Android `BACKEND_BASE_URL`도 같이 변경한다. `0.0.0.0`은 서버 bind 주소이므로 Android URL로 쓰지 않는다.

## 빠른 상태 확인

서버 실행 후 다른 터미널에서 확인한다.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/sessions \
  -H 'Content-Type: application/json' \
  -d '{"currency":"KRW"}'
```

정상 결과는 health `200 {"status":"ok"}`, session 생성 `201`이다.

## 테스트

일반 테스트는 로컬 `.env`와 격리되어 Mock Provider만 사용하며 OpenAI API를 호출하지 않는다.

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
```

Android UI만 확인할 때는 서버 실행 시 Mock을 명시할 수 있다.

```bash
RECOGNITION_PROVIDER=mock .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 핵심 API

- `GET /health`
- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{sessionId}/recognize`
- `GET /api/v1/sessions/{sessionId}/products`
- `POST /api/v1/sessions/{sessionId}/complete`

나머지 DTO와 endpoint는 [API contract](docs/API_CONTRACT.md)를 따른다.

## 남기는 구현

- `OpenAIRecognitionProvider`: 실제 시연 인식
- `MockRecognitionProvider`: 테스트와 Android 상태 검증
- PostgreSQL + Alembic: session/catalog 저장
- FastAPI `/api/v1`: Android 고정 contract

## 제외하는 구현

- OpenCLIP / Torch
- pgvector / local embedding index
- benchmark server/version
- 원본 crop 저장
- Web UI / SSE / WebSocket

## 문서

1. [Requirements](docs/REQUIREMENTS.md)
2. [Architecture](docs/ARCHITECTURE.md)
3. [API contract](docs/API_CONTRACT.md)
4. [Recognition](docs/RECOGNITION.md)
5. [Android integration](docs/APP_INTEGRATION.md)

OpenAI SDK와 API key 설정은 [공식 OpenAI quickstart](https://developers.openai.com/api/docs/quickstart)를 따른다.

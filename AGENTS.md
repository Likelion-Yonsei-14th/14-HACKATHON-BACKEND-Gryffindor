# AGENTS.md

이 저장소에서 작업하는 Codex/개발 에이전트는 아래 원칙을 따른다.

## 1. 먼저 읽을 문서

구현 전에 반드시 다음 순서로 읽는다.

1. `docs/REQUIREMENTS.md`
2. `docs/ARCHITECTURE.md`
3. `docs/API_CONTRACT.md`
4. `docs/DATA_MODEL.md`
5. `docs/DEVELOPMENT_PLAN.md`

API 또는 DTO를 변경할 때는 `docs/API_CONTRACT.md`를 먼저 수정한다.

## 2. 구현 경계

### Backend 책임

- OpenAI 기반 상품 식별
- 상품 Catalog 조회
- 가격/환급/환율 정보 생성
- Shopping Session 저장
- 구매/관심 상태 저장
- Travel Plan 저장
- 체크리스트 생성
- 공항 추천

### Android App 책임

- Meta DAT 연결
- 카메라 스트림
- Object Detection / Tracking
- Bounding Box 계산
- 중앙 시야 판정
- 화면 점유율 계산
- dwell time 계산
- UI / 화면 상태

Backend에서 Meta DAT, Android Camera, ML Kit 코드를 구현하지 않는다.

## 3. 구현 금지

새 요구가 명시되지 않는 한 다음을 추가하지 않는다.

- OpenCLIP
- Torch
- pgvector
- VectorSearcher
- SSE
- WebSocket
- Web Frontend
- 로그인/회원가입
- 별도 추천 LLM

## 4. API 안정성

2026-08-17 UI 병렬 작업을 위해 다음을 지킨다.

- `/api/v1` DTO는 가능한 한 backward-compatible하게 유지한다.
- 필드명을 임의로 변경하지 않는다.
- Scripted Provider와 External Provider는 동일한 응답 DTO를 사용한다.
- 실제 데이터 연동 전에도 Scripted Mode에서 모든 화면 흐름이 동작해야 한다.

## 5. OpenAI

- API Key는 환경 변수에서만 읽는다.
- 이미지 인식 결과는 자유 텍스트 파싱이 아니라 Structured Output schema로 제한한다.
- 모델명은 환경 변수로 교체 가능하게 한다.
- 실시간 영상 전체를 OpenAI로 전송하지 않는다. 앱에서 gating된 단일 crop만 받는다.
- 실제 OpenAI 호출 테스트는 opt-in으로 두고 일반 CI 테스트에서는 scripted provider를 사용한다.

## 6. 데이터

- PostgreSQL + SQLAlchemy + Alembic을 기본으로 한다.
- `(session_id, product_id)`는 중복 상품 방지를 위해 unique하게 관리한다.
- 금액은 float 대신 정수 KRW 또는 Decimal을 사용한다.
- 시간은 UTC로 저장한다.

## 7. 완료 조건

기능 구현은 아래가 모두 충족되어야 완료로 본다.

- API contract와 일치한다.
- happy path test가 있다.
- 실패 케이스가 정의되어 있다.
- Scripted Mode와 External Mode의 DTO가 동일하다.
- Swagger/OpenAPI에서 직접 검증 가능하다.

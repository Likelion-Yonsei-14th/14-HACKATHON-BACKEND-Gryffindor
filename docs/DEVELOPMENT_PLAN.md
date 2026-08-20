# Development Plan

## 목표 일정

### 2026-08-15 ~ 2026-08-17

Backend와 Android 기능 흐름을 끝까지 관통시키는 것이 목표다.

UI 완성도보다 API contract와 실제 인식 pipeline을 우선한다.

### 2026-08-17

Android UI 담당자가 실제 디자인으로 교체하는 동안 Backend 담당자는 Scripted Provider를 실제 데이터/로직으로 교체한다.

양쪽 작업이 충돌하지 않도록 8월 16일까지 API DTO를 동결한다.

---

# Stage 0. Repository Bootstrap

구현:

- FastAPI project
- `/health`
- settings / environment
- PostgreSQL connection
- SQLAlchemy
- Alembic
- pytest
- Docker Compose PostgreSQL

완료 기준:

- 서버 실행 가능
- Swagger 접근 가능
- DB migration 실행 가능
- 테스트 실행 가능

---

# Stage 1. API Contract + Scripted Vertical Slice

**가장 먼저 구현한다.**

구현:

- Session create/complete
- Product seed 5~10개
- `ScriptedRecognitionProvider`
- `/sessions/{id}/recognize`
- Session Product upsert
- Estimated Pricing
- Product list

흐름:

```text
POST session
→ scripted recognition
→ Product lookup
→ Estimated PriceQuote
→ SessionProduct save
→ ProductCard response
```

완료 기준:

- OpenAI 없이 전체 API contract를 Swagger에서 검증 가능
- 동일 상품 반복 인식 시 DB row 중복 없음
- Android UI가 이 contract만 보고 개발 가능

---

# Stage 2. OpenAI Recognition

구현:

- `RecognitionProvider` protocol
- `OpenAIRecognitionProvider`
- image input
- Pydantic 기반 structured result
- Catalog allowlist validation
- timeout/error mapping

완료 기준:

- 실제 상품 이미지 → 올바른 `product_id`
- 비상품/미등록 상품 → `UNKNOWN`
- 애매한 이미지 → `AMBIGUOUS`
- API response는 Scripted Provider와 동일

---

# Stage 3. Android End-to-End Integration

Backend 측 작업:

- multipart upload 안정화
- observation metadata validation
- CORS가 필요한 경우 개발 환경만 최소 설정
- Android device가 접근 가능한 dev server 제공
- 요청/응답 로그에 request id 추가

Android 측 예상 흐름:

```text
Meta DAT
→ Object Detection
→ Center/Occupancy/Dwell
→ Crop
→ /recognize
→ Product Card
```

완료 기준:

- 실제 Android 앱 요청을 Backend가 받음
- OpenAI 실제 인식 결과가 앱에 표시됨

---

# Stage 4. Shopping Review + Travel

구현:

- session complete
- purchase / interest review
- Travel Plan
- Rule-based Refund Checklist
- Airport Catalog fixture
- Rule-based Recommendation

완료 기준:

다음 앱 화면이 모두 API로 연결 가능하다.

```text
Shopping
→ Review
→ Travel
→ Checklist
→ Recommendation
```

---

# Stage 5. 2026-08-16 Contract Freeze

8월 16일 종료 전 수행한다.

- `/api/v1` endpoint 확정
- Request/Response schema 확정
- enum 확정
- sample JSON 정리
- Swagger 확인
- Scripted Mode로 모든 화면 데이터 반환 확인

이 시점 이후 UI 팀은 Backend 내부 구현과 무관하게 작업할 수 있어야 한다.

---

# Stage 6. 2026-08-17 Parallel Work

## UI 팀

Backend contract를 변경하지 않고 다음을 수행한다.

- 임시 Material UI 제거
- 실제 디자인 적용
- 화면 transition 개선
- loading / empty / error state

## Backend 담당

동시에 Scripted Provider를 실제 구현으로 교체한다.

우선순위:

1. OpenAI Recognition Provider 실제 사용
2. 실제 상품 Catalog
3. 환율 Provider
4. 검증된 범위 내 환급 계산 Provider
5. 공항 Catalog 데이터 개선
6. 영수증 인식 (시간이 남을 경우)

Provider 교체로 API DTO가 바뀌어서는 안 된다.

---

# Stage 7. MVP Hardening

구현:

- timeout fallback
- OpenAI failure 처리
- 중복 request 방지
- catalog seed command
- local data reset command
- structured logging
- API latency 측정

필수 fallback:

```text
OpenAI failure
→ 앱 crash X
→ RECOGNITION_PROVIDER_ERROR 또는 재시도 가능한 상태 반환
```

---

# 작업 우선순위

## P0

- API contract
- Scripted vertical slice
- OpenAI Recognition
- Session Product 저장
- Product Price DTO
- Shopping Review
- Travel Plan
- Checklist
- Rule Recommendation
- Android integration

## P1

- Live FX
- 실제 환급 policy
- Receipt recognition
- 실제 airport catalog

## P2

- Production-scale product retrieval
- 사용자 계정
- recommendation ML
- analytics dashboard

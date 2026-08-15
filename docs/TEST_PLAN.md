# Test Plan

## 1. 목표

MVP에서 가장 중요한 것은 "정확한 기능 수"보다 하나의 사용자 흐름이 안정적으로 끝까지 동작하는 것이다.

테스트는 다음 세 계층으로 나눈다.

- Unit
- API Integration
- Real Device Smoke

## 2. Unit Test

### Session

- session 생성 → ACTIVE
- complete → COMPLETED
- completed session에서 recognize 거부

### Session Product

- 첫 MATCHED → row 생성
- 같은 product 반복 → row 증가 X
- observation_count 증가
- max occupancy/dwell 갱신

### Pricing

- KRW 가격 입력 → refund quote 생성
- currency conversion 결과 schema 유지
- provider error handling

### Review

- purchased 저장
- interested 저장
- purchased/interested 중복 입력 시 purchased 우선
- 세션에 없는 product 선택 거부

### Recommendation

- purchased → CROSS_SELL
- interested → REMINDER
- airport catalog 밖 상품 제외

## 3. Recognition Provider Test

일반 CI에서는 OpenAI를 호출하지 않는다.

### Mock Provider

- MATCHED fixture
- AMBIGUOUS fixture
- UNKNOWN fixture
- provider exception

### OpenAI Provider

별도 opt-in smoke test로 수행한다.

- 로컬 Catalog reference와 별도 촬영 query → `MATCHED`
- 상품과 무관한 query → `UNKNOWN`
- 유사 상품 ambiguity
- invalid structured result fallback

## 4. API Integration

### Vertical Slice

```text
POST /sessions
→ POST /recognize
→ GET /products
→ POST /complete
→ PUT /review
→ PUT /travel
→ GET /refund-checklist
→ GET /recommendations
```

전체 flow를 하나의 integration test로 유지한다.

## 5. Contract Test

UI 병렬 작업을 위해 주요 response를 snapshot 또는 schema test로 고정한다.

반드시 보호할 DTO:

- SessionResponse
- RecognitionResponse
- ObservedProductResponse
- PriceQuoteResponse
- RefundChecklistResponse
- RecommendationResponse

## 6. Real Device Smoke Test

Android 실제 기기 + Meta Gen2에서 최소 다음을 확인한다.

1. 쇼핑 시작
2. 관심 trigger 발생
3. crop upload
4. recognition 반환
5. 상품 카드 자동 표시
6. 동일 상품 중복 카드 없음
7. 쇼핑 종료
8. 구매/관심 선택
9. Travel 저장
10. Checklist/Recommendation 표시

## 7. 성능 측정

초기에는 엄격한 SLA보다 체감 latency를 기록한다.

기록할 구간:

```text
Android trigger time
→ Backend request received
→ OpenAI request start
→ OpenAI response
→ Backend response
→ App render
```

Backend는 최소 다음 값을 로그에 남긴다.

- request_id
- session_id
- endpoint
- provider
- recognition latency
- total latency
- result status

이미지 원본 자체를 로그로 저장하지 않는다.

## 8. Demo Acceptance

시연 전 최소 10회의 연속 full-flow에서 다음을 만족해야 한다.

- 서버 crash 없음
- session/product 중복 오류 없음
- API schema 변경 없음
- OpenAI 실패 시 앱 crash 없음
- Mock Mode 전환 가능
- demo reset 가능

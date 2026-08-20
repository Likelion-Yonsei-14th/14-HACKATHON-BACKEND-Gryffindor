# Architecture

## 1. 핵심 결정

본 프로젝트는 **Android App + Backend**의 2-tier application structure를 사용한다.

별도 Web Frontend는 존재하지 않는다.

```text
┌──────────────── Android App ────────────────┐
│ Meta DAT                                    │
│ Camera Stream                               │
│ Object Detection / Tracking                 │
│ Center ROI / Occupancy / Dwell              │
│ UI / Navigation / Local State               │
└──────────────────┬──────────────────────────┘
                   │ HTTPS
                   ▼
┌──────────────── FastAPI ────────────────────┐
│ API Layer                                   │
│                                             │
│ Application Services                        │
│ ├─ RecognitionService                       │
│ ├─ PricingService                           │
│ ├─ ShoppingSessionService                   │
│ ├─ RefundChecklistService                   │
│ └─ RecommendationService                    │
│                                             │
│ Providers                                   │
│ ├─ RecognitionProvider                      │
│ │   ├─ ScriptedRecognitionProvider           │
│ │   ├─ OpenCLIPRecognitionProvider           │
│ │   └─ OpenAIRecognitionProvider             │
│ ├─ FxRateProvider                           │
│ ├─ RefundPolicyProvider                     │
│ └─ AirportCatalogProvider                   │
│                                             │
│ Repository                                  │
│ └─ PostgreSQL / SQLAlchemy                  │
└──────────────────┬──────────────────────────┘
                   ▼
               PostgreSQL
```

## 2. Android와 Backend 경계

### Android App이 담당한다

```text
Meta Gen2
→ DAT Camera Frame
→ Object Detection
→ Bounding Box
→ Center ROI 판정
→ Occupancy Ratio 계산
→ Dwell 계산
→ Trigger 만족
→ Product Crop 생성
```

### Backend가 담당한다

```text
Product Crop
→ OpenAI Recognition
→ product_id
→ Product Catalog
→ Pricing
→ Session Product Upsert
→ API Response
```

Backend는 프레임 스트림 전체를 받지 않는다.

## 3. Recognition 경계

Recognition 핵심 계약은 다음과 같다.

```text
RecognitionInput
- image
- catalog candidates

RecognitionResult
- status: MATCHED | AMBIGUOUS | UNKNOWN
- product_id: optional
- candidate_product_ids: optional
```

`RecognitionService`는 OpenAI SDK 세부사항을 직접 노출하지 않는다.

```text
RecognitionService
       ↓
RecognitionProvider protocol
       ├─ ScriptedRecognitionProvider
       ├─ OpenCLIPRecognitionProvider
       └─ OpenAIRecognitionProvider
```

이 구조를 사용하여 UI 병렬 작업 중에는 Scripted Provider를 사용하고, 실제 시연에서는 OpenAI Provider로 전환한다.

## 4. Pricing 경계

가격 정보는 상품 식별과 분리한다.

```text
Product
  ↓
PricingService
  ├─ RefundPolicyProvider
  └─ FxRateProvider
  ↓
PriceQuote
```

`RecognitionProvider`가 가격, 세금, 환율을 계산하지 않는다.

## 5. Recommendation 경계

P0 추천은 rule-based다.

```text
SessionProduct
├─ PURCHASED
│    → cross-sell rule
└─ INTERESTED
     → reminder rule

+ airport_code
→ AirportCatalogProvider
→ RecommendationResult
```

추천을 위해 별도 LLM을 호출하지 않는다.

## 6. Scripted / External 교체 구조

2026-08-17 UI 병렬 작업 전까지 API 계약을 고정한다.

```text
                  ┌─ ScriptedRecognitionProvider
API → Service ────┼─ OpenCLIPRecognitionProvider
                  └─ OpenAIRecognitionProvider

                  ┌─ FixedFxRateProvider
PricingService ───┤
                  └─ LiveFxRateProvider (P1)

                  ┌─ ConfigRefundPolicyProvider
                  └─ VerifiedRefundPolicyProvider (P1)
```

Provider가 바뀌어도 API Response DTO는 변경하지 않는다.

## 7. 데이터 흐름

### 쇼핑 중

```text
POST /sessions
→ ACTIVE session

Android interest trigger
→ POST /sessions/{id}/recognize
→ RecognitionProvider
→ Product lookup
→ PricingService
→ SessionProduct upsert
→ ProductCard DTO
```

### 쇼핑 종료 후

```text
POST /sessions/{id}/complete
→ COMPLETED

PUT /sessions/{id}/review
→ purchase / interest status

PUT /sessions/{id}/travel
→ TravelPlan

GET /sessions/{id}/refund-checklist
GET /sessions/{id}/recommendations
```

## 8. 의존성 규칙

금지되는 의존성:

```text
RecognitionService → Android / Meta DAT
RecognitionProvider → Session Repository
RecognitionProvider → PricingService
PricingService → OpenAI SDK
Repository → FastAPI Router
```

허용되는 방향:

```text
Router
→ Application Service
→ Provider / Repository
→ External API / DB
```

## 9. 배포 특성

OpenAI inference는 외부 API에서 수행하므로 Backend 서버에 GPU가 필요하지 않다.

Backend는 일반 CPU 인스턴스에서 실행 가능한 구조를 유지한다.

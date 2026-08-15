# API Contract

## 1. 원칙

- Base path: `/api/v1`
- JSON field: `camelCase`
- 서버 내부 Python model은 snake_case여도 API alias를 통해 camelCase를 유지한다.
- 시간은 ISO 8601 UTC로 반환한다.
- 금액은 KRW 정수 또는 Decimal 기반 값으로 처리한다.
- OpenAI Provider / Mock Provider 여부와 관계없이 동일한 DTO를 반환한다.
- UI 병렬 작업 시작 후 기존 필드 삭제·이름 변경을 피한다.

## 2. Health

### `GET /health`

```json
{
  "status": "ok"
}
```

---

## 3. Shopping Session

### `POST /api/v1/sessions`

Request:

```json
{
  "currency": "CNY"
}
```

Response `201`:

```json
{
  "sessionId": "uuid",
  "status": "ACTIVE",
  "currency": "CNY",
  "startedAt": "2026-08-15T13:30:00Z"
}
```

### `POST /api/v1/sessions/{sessionId}/complete`

Response:

```json
{
  "sessionId": "uuid",
  "status": "COMPLETED",
  "completedAt": "2026-08-15T14:10:00Z"
}
```

---

## 4. Recognition + Observation

### `POST /api/v1/sessions/{sessionId}/recognize`

Content-Type: `multipart/form-data`

Fields:

- `image`: JPEG/PNG crop
- `capturedAt`: ISO 8601
- `triggerType`: `OCCUPANCY` | `DWELL` | `OCCUPANCY_AND_DWELL`
- `occupancyRatio`: 0.0 ~ 1.0
- `dwellMs`: integer >= 0
- `trackingId`: optional string

Backend는 `occupancyRatio`를 다시 CV로 계산하지 않는다. 범위 validation과 기록만 수행한다.

### Match Response

```json
{
  "recognitionStatus": "MATCHED",
  "isNew": true,
  "observedProduct": {
    "product": {
      "productId": "mcm_001",
      "sku": "SKU001",
      "brand": "MCM",
      "name": "Product Name",
      "category": "bag",
      "imageUrl": "https://example.com/product.jpg"
    },
    "pricing": {
      "retailPriceKrw": 1090000,
      "estimatedRefundKrw": 60000,
      "estimatedRefundPriceKrw": 1030000,
      "convertedAmount": "5210.35",
      "convertedCurrency": "CNY",
      "instantRefundEligible": true,
      "pricingMode": "MOCK"
    },
    "observation": {
      "triggerType": "OCCUPANCY_AND_DWELL",
      "occupancyRatio": 0.24,
      "dwellMs": 1500,
      "firstObservedAt": "2026-08-15T13:35:00Z",
      "lastObservedAt": "2026-08-15T13:35:00Z"
    }
  }
}
```

### Ambiguous Response

```json
{
  "recognitionStatus": "AMBIGUOUS",
  "candidateProductIds": ["mcm_001", "mcm_002"]
}
```

### Unknown Response

```json
{
  "recognitionStatus": "UNKNOWN"
}
```

`AMBIGUOUS`, `UNKNOWN`은 세션 상품에 자동 저장하지 않는다.

---

## 5. Session Product List

### `GET /api/v1/sessions/{sessionId}/products`

Response:

```json
{
  "sessionId": "uuid",
  "items": [
    {
      "product": {
        "productId": "mcm_001",
        "sku": "SKU001",
        "brand": "MCM",
        "name": "Product Name",
        "category": "bag",
        "imageUrl": "https://example.com/product.jpg"
      },
      "pricing": {
        "retailPriceKrw": 1090000,
        "estimatedRefundKrw": 60000,
        "estimatedRefundPriceKrw": 1030000,
        "convertedAmount": "5210.35",
        "convertedCurrency": "CNY",
        "instantRefundEligible": true,
        "pricingMode": "MOCK"
      },
      "purchaseState": "UNSET",
      "interested": false
    }
  ]
}
```

---

## 6. Shopping Review

### `PUT /api/v1/sessions/{sessionId}/review`

Request:

```json
{
  "purchasedProductIds": ["mcm_001"],
  "interestedProductIds": ["mcm_002"]
}
```

규칙:

- purchased와 interested가 동시에 들어온 상품은 `PURCHASED`를 우선한다.
- 세션에 존재하지 않는 productId는 `400`으로 거절한다.

Response:

```json
{
  "purchasedProductIds": ["mcm_001"],
  "interestedProductIds": ["mcm_002"]
}
```

---

## 7. Travel Plan

### `PUT /api/v1/sessions/{sessionId}/travel`

Request:

```json
{
  "airportCode": "ICN",
  "flightNumber": "KE123",
  "airportArrivalAt": "2026-08-18T01:30:00Z"
}
```

Response:

```json
{
  "airportCode": "ICN",
  "flightNumber": "KE123",
  "airportArrivalAt": "2026-08-18T01:30:00Z"
}
```

---

## 8. Refund Checklist

### `GET /api/v1/sessions/{sessionId}/refund-checklist`

Response:

```json
{
  "items": [
    {
      "id": "keep-receipt",
      "title": "구매 영수증을 준비하세요",
      "description": "환급 확인을 위해 구매 증빙을 준비합니다.",
      "required": true
    }
  ],
  "mode": "MOCK"
}
```

체크 완료 상태는 P0에서는 앱 로컬 상태로 관리해도 된다.

---

## 9. Airport Recommendation

### `GET /api/v1/sessions/{sessionId}/recommendations`

Response:

```json
{
  "airportCode": "ICN",
  "items": [
    {
      "type": "CROSS_SELL",
      "sourceProductId": "mcm_001",
      "product": {
        "productId": "mcm_010",
        "sku": "SKU010",
        "brand": "MCM",
        "name": "Recommended Product",
        "category": "wallet",
        "imageUrl": "https://example.com/recommended.jpg"
      },
      "reasonCode": "SAME_BRAND_DIFFERENT_CATEGORY"
    },
    {
      "type": "REMINDER",
      "sourceProductId": "mcm_002",
      "product": {
        "productId": "mcm_002",
        "sku": "SKU002",
        "brand": "MCM",
        "name": "Interested Product",
        "category": "bag",
        "imageUrl": "https://example.com/interested.jpg"
      },
      "reasonCode": "INTERESTED_NOT_PURCHASED"
    }
  ],
  "mode": "MOCK"
}
```

---

## 10. Common Errors

```json
{
  "error": {
    "code": "SESSION_NOT_ACTIVE",
    "message": "Recognition is allowed only for an active shopping session."
  }
}
```

권장 error code:

- `SESSION_NOT_FOUND`
- `SESSION_NOT_ACTIVE`
- `INVALID_IMAGE`
- `RECOGNITION_PROVIDER_ERROR`
- `PRODUCT_NOT_FOUND`
- `INVALID_PRODUCT_SELECTION`
- `TRAVEL_PLAN_REQUIRED`
- `AIRPORT_CATALOG_UNAVAILABLE`

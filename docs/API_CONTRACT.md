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

## 3. Store Catalog

### `GET /api/v1/stores`

Response `200`:

```json
{
  "stores": [
    {
      "id": "10000000-0000-0000-0000-000000000001",
      "name": "MCM Seoul",
      "brand": "MCM",
      "country": "KR",
      "city": "Seoul",
      "type": "CITY",
      "airportCode": null
    }
  ]
}
```

---

## 4. Shopping Session

### `POST /api/v1/sessions`

Request:

```json
{
  "currency": "CNY",
  "storeId": "10000000-0000-0000-0000-000000000001"
}
```

`currency`는 사용자가 선택한 국가의 통화이며 미국은 `USD`, 중국은 `CNY`를 사용한다.
Android는 가격 응답에 함께 포함되는 KRW 금액과 이 대상 통화 금액을 상단 토글로 전환한다.
`storeId`는 `GET /api/v1/stores`에서 조회한 매장 UUID이며 필수다.
존재하지 않는 UUID를 보내면 `404 STORE_NOT_FOUND`를 반환한다.

Response `201`:

```json
{
  "sessionId": "uuid",
  "status": "ACTIVE",
  "currency": "CNY",
  "storeId": "10000000-0000-0000-0000-000000000001",
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

## 5. Recognition + Observation

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
      "estimatedRefundKrw": 76000,
      "estimatedRefundPriceKrw": 1014000,
      "convertedRetailPrice": "5513.86",
      "convertedEstimatedRefund": "384.45",
      "convertedEstimatedRefundPrice": "5129.41",
      "convertedAmount": "5129.41",
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

## 6. Session Product List

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
        "estimatedRefundKrw": 76000,
        "estimatedRefundPriceKrw": 1014000,
        "convertedRetailPrice": "5513.86",
        "convertedEstimatedRefund": "384.45",
        "convertedEstimatedRefundPrice": "5129.41",
        "convertedAmount": "5129.41",
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

가격 응답 규칙:

- `retailPriceKrw`, `estimatedRefundKrw`는 상품 DB의 KRW 고정값이다.
- `estimatedRefundPriceKrw`는 두 고정값의 차이며 별도 DB 컬럼으로 저장하지 않는다.
- `convertedRetailPrice`, `convertedEstimatedRefund`, `convertedEstimatedRefundPrice`는 세션의
  `currency`와 `ExchangeRateService`의 DB 캐시 환율로 계산한 Decimal 문자열이다.
- 기존 Android 호환성을 위해 `convertedAmount`는 `convertedEstimatedRefundPrice`와 같은 값을 유지한다.
- 상품 API 요청은 외부 환율 API를 호출하지 않는다.
- 환율 캐시가 없더라도 KRW 가격과 recognition 결과는 정상 반환한다.
  `convertedRetailPrice`, `convertedEstimatedRefund`, `convertedEstimatedRefundPrice`,
  `convertedAmount`만 `null` 또는 미제공될 수 있으며 `convertedCurrency`는 선택 통화를 유지한다.

---

## 7. Shopping Review

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

## 8. Travel Plan

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

## 9. Refund Checklist

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

## 10. Airport Recommendation

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

## 11. Common Errors

```json
{
  "error": {
    "code": "SESSION_NOT_ACTIVE",
    "message": "Recognition is allowed only for an active shopping session."
  }
}
```

권장 error code:

- `INVALID_REQUEST`
- `SESSION_NOT_FOUND`
- `STORE_NOT_FOUND`
- `SESSION_NOT_ACTIVE`
- `INVALID_IMAGE`
- `RECOGNITION_PROVIDER_ERROR`
- `PRODUCT_NOT_FOUND`
- `INVALID_PRODUCT_SELECTION`
- `TRAVEL_PLAN_REQUIRED`
- `AIRPORT_CATALOG_UNAVAILABLE`

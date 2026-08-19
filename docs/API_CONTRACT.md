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
- `DOCUMENT_EXTRACTION_PROVIDER_ERROR`
- `RECOMMENDATION_PROVIDER_ERROR`
- `FLIGHT_NOT_FOUND`

---

## 12. Demo User Personalization

모든 `/api/v1/me` API는 인증 없이 고정된 Demo User(`id=1`)를 사용한다.

### `GET /api/v1/me/wishlist`

Response `200`:

```json
{
  "items": [
    {
      "productId": "demo_perfume_001",
      "sku": "DEMO-DIPTYQUE-PAPIER-100",
      "brand": "Diptyque",
      "name": "로 파피에 오 드 뚜왈렛 100ml",
      "category": "perfume",
      "imageUrl": "https://example.com/product.jpg"
    }
  ]
}
```

### `POST /api/v1/me/wishlist/{productId}`

존재하지 않는 상품은 `404 PRODUCT_NOT_FOUND`를 반환한다. 이미 저장된 상품은 새 row를
만들지 않으며 동일한 Product DTO를 `200`으로 반환한다.

### `DELETE /api/v1/me/wishlist/{productId}`

존재 여부와 관계없이 `204`를 반환한다.

### `POST /api/v1/me/receipts/analyze`

Content-Type: `multipart/form-data`, field: `image` (JPEG/PNG)

Response `201`:

```json
{
  "id": "uuid",
  "storeName": "THE HYUNDAI SEOUL",
  "purchasedAt": "2026-08-19T05:30:00Z",
  "totalAmount": 850000,
  "currency": "KRW",
  "items": [
    {
      "name": "Stark Backpack",
      "productId": null,
      "quantity": 1,
      "price": 850000
    }
  ],
  "createdAt": "2026-08-19T05:30:01Z"
}
```

이 endpoint는 영수증 문서 보관이 아니라 구매 상품 등록(Purchase Capture)을 수행한다.
분석 성공 시 구매 이벤트와 구매 상품을 즉시 저장하며, 원본 이미지는 저장하지 않는다.
상품명은 Catalog의 정규화된 정확한 이름과 유일하게 일치할 때만 `productId`를 연결한다.
일치하지 않는 상품도 OCR 원문 이름과 함께 저장한다. 응답 형식은 기존 Android 호환성을
위해 유지한다.

### `GET /api/v1/me/purchases`

영수증 문서가 아닌 구매 이벤트 단위로 구매 상품을 조회한다.

Response `200`:

```json
[
  {
    "id": "uuid",
    "storeName": "THE HYUNDAI SEOUL",
    "purchasedAt": "2026-08-19T05:30:00Z",
    "totalAmount": 1093450,
    "currency": "KRW",
    "items": [
      {
        "purchaseItemId": "uuid",
        "product": null,
        "fallbackProductName": "준지_남성",
        "quantity": 1,
        "price": 621000
      }
    ],
    "createdAt": "2026-08-19T05:30:01Z"
  }
]
```

Catalog 매칭에 성공하면 `product`에 기존 Product DTO를 반환하고
`fallbackProductName`은 `null`이다. 매칭에 실패하면 `product`는 `null`이고 OCR에서 읽은
상품명을 `fallbackProductName`에 그대로 반환한다.

### `POST /api/v1/me/flights/analyze`

Content-Type: `multipart/form-data`, field: `image` (JPEG/PNG)

Response `201`:

```json
{
  "id": "uuid",
  "departureAirport": "ICN",
  "arrivalAirport": "JFK",
  "terminal": null,
  "flightNumber": "KE081",
  "departureAt": "2026-08-21T01:00:00Z",
  "arrivalAt": null,
  "airportArrivalAt": null,
  "createdAt": "2026-08-19T05:31:00Z"
}
```

OCR은 `departureAirport`, `arrivalAirport`, `terminal`, `flightNumber`, `departureAt`,
`arrivalAt`만 추출한다. 이미지에서 확인할 수 없는 값은 `null`이다. `airportArrivalAt`은
사용자 계획 값이므로 분석 직후에는 항상 `null`이다.

### `PATCH /api/v1/me/flights/{flightId}`

OCR 누락 값과 사용자가 직접 계획하는 공항 도착 예정시간을 부분 수정한다. 모든 필드는
선택 사항이며 명시적으로 `null`을 보내 기존 값을 지울 수 있다.

Request 예시:

```json
{
  "terminal": "T2",
  "departureAt": "2026-08-21T10:00:00+09:00",
  "arrivalAt": "2026-08-21T13:30:00+08:00",
  "airportArrivalAt": "2026-08-21T07:00:00+09:00"
}
```

Response `200`: 수정된 Flight DTO. 존재하지 않거나 Demo User 소유가 아니면
`404 FLIGHT_NOT_FOUND`를 반환한다.

### `GET /api/v1/me/recommendations`

OpenAI에는 Wishlist, SessionProduct 관심 이력, 구매 상품, 최신 Flight와 DB의
`store_products` 관계에서 만든 후보만 전달한다. Catalog에 매칭된 구매 상품은 exact product
후보에서 제외한다. 매칭되지 않은 구매 상품은 OCR 상품명과 매장명만 취향 문맥으로 전달한다.
OpenAI 결과의 Store/Product ID와 소속 관계를 다시 검증하고 유효하지 않은 항목은 응답에서
제거한다.

Response `200`:

```json
{
  "stores": [
    {
      "storeId": "10000000-0000-0000-0000-000000000003",
      "name": "MCM Airport Store",
      "reason": "출국 전에 방문하기 편리한 매장입니다.",
      "products": [
        {
          "product": {
            "productId": "demo_perfume_001",
            "sku": "DEMO-DIPTYQUE-PAPIER-100",
            "brand": "Diptyque",
            "name": "로 파피에 오 드 뚜왈렛 100ml",
            "category": "perfume",
            "imageUrl": "https://example.com/product.jpg"
          },
          "reason": "Wishlist와 매장 관찰 이력에 모두 포함된 상품입니다."
        }
      ]
    }
  ]
}
```

개인화 데이터나 추천 후보가 없으면 `200 {"stores": []}`를 반환한다.

### `GET /api/v1/me`

Recommendation provider를 호출하지 않고 저장 데이터만 집계한다.

Response `200`:

```json
{
  "user": {"id": 1, "name": "Demo User"},
  "wishlist": [],
  "purchasedProducts": [
    {
      "purchaseItemId": "uuid",
      "product": null,
      "fallbackProductName": "준지_남성",
      "quantity": 1,
      "price": 621000,
      "currency": "KRW",
      "storeName": "THE HYUNDAI SEOUL",
      "purchasedAt": "2026-08-19T05:30:00Z"
    }
  ],
  "flight": null
}
```

Document/Recommendation OpenAI timeout, API failure, structured response validation 실패는 각각
`503 DOCUMENT_EXTRACTION_PROVIDER_ERROR`, `503 RECOMMENDATION_PROVIDER_ERROR`로 변환한다.

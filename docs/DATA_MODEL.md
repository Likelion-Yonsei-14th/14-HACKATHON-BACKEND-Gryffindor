# Data Model

## 1. 설계 원칙

MVP에서는 사용자 계정 없이 `ShoppingSession`을 aggregate root로 사용한다.

최소 테이블은 다음 다섯 개다.

```text
products
stores
shopping_sessions
session_products
travel_plans
```

Checklist와 Recommendation은 P0에서 요청 시 계산하며 별도 저장하지 않는다.

## 2. products

```text
products
- id UUID / PK
- product_id VARCHAR / UNIQUE
- sku VARCHAR / UNIQUE
- brand VARCHAR
- name VARCHAR
- category VARCHAR
- image_url TEXT
- price_krw BIGINT
- estimated_refund_krw BIGINT
- tax_refund_supported BOOLEAN
- metadata JSONB
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ
```

`20260817_0006` 적용 시 기존 session row는 demo `MCM Seoul`로 backfill한 뒤
`store_id`를 `NOT NULL`로 전환한다.

`instant_refund_eligible`를 product의 영구 속성으로 단정하지 않는다. 최종 여부는 RefundPolicyProvider에서 현재 정책/조건을 이용해 계산한다.

MVP Mock Mode에서는 metadata에 테스트용 조건을 둘 수 있다.

`price_krw`와 `estimated_refund_krw`는 seed/product 데이터의 미리 계산된 KRW 고정값이다.
예상 환급 후 가격은 `price_krw - estimated_refund_krw`로 계산하며 중복 저장하지 않는다.

## 3. stores

```text
stores
- id UUID / PK
- name VARCHAR
- brand VARCHAR
- country VARCHAR
- city VARCHAR
- type VARCHAR
- airport_code VARCHAR NULL
```

`type`은 현재 demo에서 `CITY`, `AIRPORT`를 사용한다. 공항 매장은 `airport_code`를
사용하며 일반 매장은 `NULL`일 수 있다.

## 4. shopping_sessions

```text
shopping_sessions
- id UUID / PK
- store_id UUID / FK / NOT NULL
- status ENUM(ACTIVE, COMPLETED)
- currency CHAR(3)
- started_at TIMESTAMPTZ
- completed_at TIMESTAMPTZ NULL
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ
```

## 5. session_products

한 세션에서 한 상품은 한 row만 가진다.

```text
session_products
- id UUID / PK
- session_id UUID / FK
- product_id UUID / FK
- first_observed_at TIMESTAMPTZ
- last_observed_at TIMESTAMPTZ
- max_occupancy_ratio NUMERIC
- max_dwell_ms INTEGER
- last_trigger_type ENUM(OCCUPANCY, DWELL, OCCUPANCY_AND_DWELL)
- observation_count INTEGER
- purchase_state ENUM(UNSET, PURCHASED)
- interested BOOLEAN
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

UNIQUE(session_id, product_id)
```

반복 인식 시 새 row를 만들지 않고 아래를 update한다.

- `last_observed_at`
- `max_occupancy_ratio`
- `max_dwell_ms`
- `last_trigger_type`
- `observation_count`

## 6. travel_plans

```text
travel_plans
- id UUID / PK
- session_id UUID / FK / UNIQUE
- airport_code VARCHAR
- flight_number VARCHAR
- airport_arrival_at TIMESTAMPTZ
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ
```

## 7. Demo Seed

Demo 매장은 `data/stores.seed.json`, 시연 상품은 `data/products.seed.json` 형태로
관리하고 각각의 seed command로 DB에 입력한다.

Store seed에는 Android E2E용 `MCM Seoul`, `MCM New York`, `MCM Airport Store`를
포함한다.

### Product Seed

예:

```json
[
  {
    "productId": "catalog_001",
    "sku": "SKU001",
    "brand": "Example Brand",
    "name": "Product Name",
    "category": "bag",
    "imageUrl": "https://example.com/product.jpg",
    "priceKrw": 1090000,
    "estimatedRefundKrw": 76000,
    "taxRefundSupported": true
  }
]
```

## 8. Airport Catalog

P0에서는 별도 테이블을 만들지 않아도 된다.

```text
data/airport_catalog.seed.json
```

형태로 다음 관계만 제공한다.

```text
airport_code
→ available product_ids
```

실제 데이터 소스가 확보되면 `AirportCatalogProvider` 구현만 교체한다.

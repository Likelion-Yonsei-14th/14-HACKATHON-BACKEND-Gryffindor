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

`instant_refund_eligible`를 product의 영구 속성으로 단정하지 않는다. Product Card에서는
`tax_refund_supported`와 개별 상품 가격 1,000,000원 미만 조건만으로 잠재 가능성을 계산하고,
Purchase의 실제 거래 총액과 누적 금액은 Refund Checklist에서 별도로 계산한다.

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

## 9. B5 Demo User Personalization

인증은 추가하지 않고 모든 `/me` API와 새 Shopping Session은 고정 Demo User `id=1`을
사용한다. 기존 Shopping Session은 migration에서 Demo User로 backfill한다.

```text
users
- id INTEGER / PK
- name VARCHAR
- created_at TIMESTAMPTZ

wishlist_items
- id UUID / PK
- user_id INTEGER / FK
- product_id UUID / FK
- created_at TIMESTAMPTZ

UNIQUE(user_id, product_id)
```

## 10. Purchase Capture / Flight

```text
receipts
- id UUID / PK
- user_id INTEGER / FK
- trip_id UUID / FK NULL
- refund_method VARCHAR(16) / UNKNOWN | IMMEDIATE | DOWNTOWN | AIRPORT
- store_name VARCHAR NULL
- purchased_at TIMESTAMPTZ NULL
- total_amount BIGINT NULL
- currency VARCHAR(3) NULL
- image_path TEXT NULL
- created_at TIMESTAMPTZ

receipt_items
- id UUID / PK
- receipt_id UUID / FK
- product_name VARCHAR
- product_id UUID / FK NULL
- quantity INTEGER NULL
- price BIGINT NULL

flights
- id UUID / PK
- user_id INTEGER / FK
- departure_airport VARCHAR(3) NULL
- arrival_airport VARCHAR(3) NULL
- terminal VARCHAR NULL
- flight_number VARCHAR NULL
- departure_at TIMESTAMPTZ NULL
- arrival_at TIMESTAMPTZ NULL
- airport_arrival_at TIMESTAMPTZ NULL
- created_at TIMESTAMPTZ
```

테이블명은 기존 migration 호환성을 위해 유지하지만 `receipts`는 영수증 문서가 아니라 구매
이벤트, `receipt_items`는 구매 상품을 뜻한다. 상품 매핑은 정규화된 상품명이 Catalog의 한
상품과 정확하고 유일하게 일치할 때만 설정한다. 매칭되지 않은 실제 구매 상품도
`product_name`을 보존하며, OCR 이미지는 저장하지 않으므로 `image_path`는 `NULL`이다.

`airport_arrival_at`은 OCR 결과가 아니라 사용자가 직접 저장하는 여행 계획 값이다. 추천은
`created_at`이 가장 최신인 Flight를 사용한다.

`receipts.trip_id`를 생략한 기존 Purchase Capture 흐름과 기존 row는 그대로 유지한다.
`refund_method`의 기존/default 값은 `UNKNOWN`이며 금액 조건만으로 실제 환급 방식을 자동
변경하지 않는다. Refund Checklist와 즉시환급 잠재 금액 조건은 요청 시 계산하며 별도
체크리스트 상태를 저장하지 않는다.

## 11. Store Product Allowlist

```text
store_products
- store_id UUID / FK / PK
- product_id UUID / FK / PK
```

추천 후보와 OpenAI 결과의 Store/Product 소속 검증은 이 관계를 기준으로 한다. B5 migration은
기존 demo Catalog가 바로 동작하도록 현재 Store와 Product 조합을 채우며, product seed도 같은
관계를 idempotent하게 보완한다. 기존 Store/Product 공개 식별자는 변경하지 않는다.

## 12. B6 Trip Shopping

```text
trips
- id UUID / PK
- user_id INTEGER / FK
- title VARCHAR
- destination_city VARCHAR NULL
- destination_country VARCHAR NULL
- starts_at TIMESTAMPTZ NULL
- ends_at TIMESTAMPTZ NULL
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

hotel_stays
- id UUID / PK
- trip_id UUID / FK / UNIQUE
- name VARCHAR
- address TEXT NULL
- latitude DOUBLE PRECISION NULL
- longitude DOUBLE PRECISION NULL
- check_in_at TIMESTAMPTZ NULL
- check_out_at TIMESTAMPTZ NULL
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

flights
+ trip_id UUID / FK NULL

stores
+ address TEXT NULL
+ latitude DOUBLE PRECISION NULL
+ longitude DOUBLE PRECISION NULL
+ terminal VARCHAR NULL
+ opening_hours TEXT NULL
```

Store의 기존 `type`, `city`, `airport_code`를 재사용한다. 기존 seed row와 공개 ID는 유지하고,
B6 seed는 `DEPARTMENT_STORE`, `DUTY_FREE` type을 사용한다.

```text
visit_reservations
- id UUID / PK
- user_id INTEGER / FK
- trip_id UUID / FK
- store_id UUID / FK
- scheduled_at TIMESTAMPTZ
- status VARCHAR(RESERVED, CANCELLED)
- created_at TIMESTAMPTZ
- updated_at TIMESTAMPTZ

visit_reservation_products
- reservation_id UUID / FK / PK
- product_id UUID / FK / PK
```

예약 상품은 생성 시 Wishlist와 StoreProduct 교집합인지 검증한다. 추천 자체는 저장하지 않고
Trip Feed 요청 시 계산한다.

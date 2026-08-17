# Android App Integration

## 1. 목적

Android 팀이 Backend 내부 구현을 몰라도 고정된 API contract만으로 UI를 구현할 수 있게 한다.

특히 2026-08-17 디자인 교체 시 Backend의 OpenAI/환급/환율 작업과 충돌하지 않는 것이 목표다.

## 2. App이 Backend에 보내기 전 수행할 것

```text
Meta Camera Frame
→ Object Detector
→ Bounding Box
→ Center ROI
→ Occupancy Ratio
→ Dwell
→ Trigger
→ Crop
```

App은 관심 조건을 통과하지 않은 frame을 Backend에 보내지 않는다.

## 3. B3 Android Producer 기준값

B3 초기 실기기 검증에서는 다음 값을 사용한다.

```text
minOccupancyRatio = 0.12
minDwellMs = 800ms
cropPaddingRatio = 0.15
minCropShortSide = 160px
jpegQuality = 85
maxCropLongSide = 1024px

bbox center:
- horizontal central 70%
- vertical central 80%
```

이 값들은 광각 Gen2 camera에서 멀리 있는 진열 상품을 걸러내기 위한 **Android-side
heuristic**이다. Android는 bbox 중심점이 앞서 정의한 중앙 영역에 있고 occupancy/dwell 조건을
만족한 대상의 padding 적용 crop만 JPEG로 만들어 Backend에 보낸다. 실기기 결과에 따라
Android 설정값으로 조정할 수 있으며 Backend가 이 기준으로 관심 여부를 재판정하지 않는다.

Backend API validation constraint는 producer 기준값과 별개다. Backend는 전달받은
`occupancyRatio`가 `0.0 <= value <= 1.0`, `dwellMs`가 `value >= 0`인지 검증하고 관찰
metadata로 기록한다.

## 4. Shopping Screen 상태

App에서 최소 다음 상태를 구분한다.

```text
IDLE
CAMERA_CONNECTED
TRACKING
RECOGNIZING
MATCHED
AMBIGUOUS
UNKNOWN
ERROR
```

Backend의 `recognitionStatus`와 UI state를 1:1로 강제하지 않는다. UI state는 앱에서 관리한다.

## 5. Recognition Request

관심 조건 만족 시 한 번 호출한다.

```text
POST /api/v1/sessions/{sessionId}/recognize
Content-Type: multipart/form-data
```

multipart fields:

```text
image           JPEG 또는 PNG crop
capturedAt      ISO 8601 timestamp
triggerType     OCCUPANCY | DWELL | OCCUPANCY_AND_DWELL
occupancyRatio  0.0 이상 1.0 이하
dwellMs         0 이상 integer
trackingId      optional string
```

`image`는 decode 가능한 단일 상품 중심 crop이어야 하며 현재 기본 최대 크기는 5 MiB다.
Android는 다음 값을 보내지 않는다.

```text
bbox coordinates
SSD detector label / confidence
전체 CameraFrame
YUV metadata
```

응답이 `MATCHED`이면 `observedProduct.product`, `pricing`, `observation`을 Product Card와
상품 목록에 반영한다. `AMBIGUOUS`이면 `candidateProductIds`를 참고해 재촬영 UX를 제공할
수 있고, `UNKNOWN`이면 상품을 추가하지 않는다. 두 상태 모두 Backend SessionProduct를
생성하지 않는다. 오류 응답은 공통 `error.code`와 `error.message` 형태로 처리한다.

## 6. 중복 처리

두 레이어에서 방어한다.

### App

- 같은 tracking target에 cooldown
- 같은 product card가 있으면 UI 중복 추가 방지

### Backend

- `UNIQUE(session_id, product_id)`
- 반복 관찰은 기존 row update

## 7. UI 병렬 작업용 Mock Mode

Backend가 `RECOGNITION_PROVIDER=mock`인 상태에서도 실제 API endpoint를 그대로 사용한다.

따라서 UI 코드는 다음과 같은 분기를 만들지 않는다.

```text
if mock:
   mockResponse()
else:
   apiCall()
```

항상 실제 HTTP endpoint를 호출하고 Backend Provider만 교체한다.

## 8. 화면별 API

### Home

```text
GET  /stores
POST /sessions
```

### Shopping

```text
POST /sessions/{id}/recognize
GET  /sessions/{id}/products
POST /sessions/{id}/complete
```

### Shopping Review

```text
PUT /sessions/{id}/review
```

### Travel / Refund

```text
PUT /sessions/{id}/travel
GET /sessions/{id}/refund-checklist
```

### Airport Recommendation

```text
GET /sessions/{id}/recommendations
```

## 9. Loading / Failure UX 계약

App은 최소 다음 실패를 처리한다.

- network timeout
- selected store not found
- recognition unknown
- recognition ambiguous
- provider temporary error
- empty product list
- travel plan missing
- airport catalog unavailable

OpenAI 오류 메시지를 그대로 사용자에게 노출하지 않는다.

## 10. 개발 환경

Android emulator와 실제 Android device에서 개발 서버 주소가 다를 수 있으므로 Base URL은 build config로 분리한다.

```text
API_BASE_URL=
```

API Key는 App config에 존재하지 않는다.

실기기용 LAN Base URL과 안전한 서버 bind 방법은 `README.md`의 "B3 Android 실기기 연결"
절을 따른다.

## 11. B3 E2E 검증 절차

1. Android에서 `GET /health`를 호출해 `200`과 `{"status":"ok"}`를 확인한다.
2. `GET /api/v1/stores`를 호출해 demo 매장 목록과 선택한 `storeId`를 얻는다.
3. `POST /api/v1/sessions`에 `{"currency":"CNY","storeId":"<선택한 UUID>"}`를
   보내 `201`과 `sessionId`를 받는다.
4. Android fixture JPEG을 위 multipart 형태로 `/recognize`에 보내 `MATCHED` 응답을
   확인한다.
5. Gen2 camera에서 `SSD detection → attention gating → bbox crop → JPEG → /recognize`
   전체 producer 흐름을 확인한다.
6. 실제 Catalog 상품으로 OpenAI recognition을 실행해 `MATCHED → productId → pricing →
   Android Product Card` 표시까지 확인한다.
7. Catalog와 무관한 이미지를 보내 `UNKNOWN`이며 상품이 추가되지 않는지 확인한다.
8. 구분하기 어려운 Catalog 상품 이미지를 보내 `AMBIGUOUS`와 `candidateProductIds`를
   확인하고 상품이 추가되지 않는지 확인한다.
9. 같은 상품을 같은 session에서 다시 인식해 `isNew=false`이며 DB의
   `(session_id, product_id)` row가 하나뿐인지 확인한다.

1~4와 Mock Provider 기반 7~9 상태/중복 검증은 automated test로 수행할 수 있다. 5~6의
Gen2 촬영과 Android UI 표시, 실제 OpenAI를 사용하는 7~8 결과 품질은 실기기 smoke
test로 최종 확인한다.

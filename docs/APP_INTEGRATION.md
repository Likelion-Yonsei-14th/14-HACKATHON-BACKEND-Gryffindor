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

## 3. 권장 Trigger Config

정확한 값은 Gen2 실제 촬영으로 보정한다.

예시 config:

```text
CENTER_ROI_WIDTH_RATIO=0.5
CENTER_ROI_HEIGHT_RATIO=0.5
MIN_OCCUPANCY_RATIO=0.20
MIN_DWELL_MS=1500
RECOGNITION_COOLDOWN_MS=3000
```

숫자는 기획 고정값이 아니라 실험 가능한 설정값이다.

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
```

전송:

- crop image
- occupancy ratio
- dwell ms
- trigger type
- capture time

응답 `MATCHED`인 경우 앱의 상품 리스트에 반영한다.

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

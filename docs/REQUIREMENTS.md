# Requirements

## 1. 목표

본 백엔드는 스마트글래스를 이용해 관광객의 오프라인 쇼핑 관심 행동을 모바일 가격 정보 및 출국 단계 추천으로 연결하는 MVP를 지원한다.

사용자가 스마트글래스로 제품을 바라보는 동안 Android 앱이 관심 행동을 판단한다. 관심 조건을 만족한 제품 이미지가 서버로 전달되면 서버는 상품을 식별하고 상품 DB와 매칭하여 가격 정보를 반환한다.

쇼핑이 끝난 뒤에는 구매 이력과 미구매 관심 이력을 구분해 저장하고, 사용자의 출국 정보를 기반으로 환급 체크리스트와 공항 추천을 제공한다.

## 2. 사용자 흐름

```text
쇼핑 시작
→ 스마트글래스 카메라 스트림
→ 앱에서 관심 행동 판정
→ 후보 제품 이미지 전송
→ 서버에서 제품 식별
→ 가격 3단 정보 반환
→ 앱 상품 목록 자동 적재
→ 쇼핑 종료
→ 구매/관심 상품 확정
→ 출국 정보 입력
→ 환급 체크리스트
→ 출국 공항 기준 추천
```

## 3. 관심 행동 판정

관심 행동 판정은 Backend가 아니라 Android App의 책임이다.

앱은 최소 다음 신호를 사용할 수 있다.

- 제품 Bounding Box 중심점이 중앙 관심 영역 안에 위치
- `bbox_area / frame_area`가 설정된 threshold 이상
- 동일 tracking 대상 또는 제품 후보가 설정 시간 이상 지속

MVP에서는 실제 eye tracking이나 손으로 제품을 들었는지 판정하지 않는다.

서버는 앱이 전달한 `occupancy_ratio`, `dwell_ms`, `trigger_type`을 검증 및 기록할 수 있으나 관심 여부를 재판정하기 위한 CV pipeline을 실행하지 않는다.

## 4. P0 기능

### 4.1 Shopping Session

- 쇼핑 세션을 시작할 수 있다.
- 상태는 `ACTIVE`, `COMPLETED`를 가진다.
- 활성 세션에만 새로운 인식 결과를 저장한다.
- 동일 상품은 한 세션에 한 번만 생성하고 이후 관찰은 갱신한다.

### 4.2 Product Recognition

- 앱으로부터 관심 조건을 통과한 제품 crop 이미지를 받는다.
- OpenAI image-capable model을 이용해 제한된 상품 Catalog 중 상품을 식별한다.
- 결과는 `MATCHED`, `AMBIGUOUS`, `UNKNOWN` 중 하나다.
- `MATCHED`일 때만 `product_id`를 확정한다.
- 자유 텍스트가 아니라 schema가 고정된 structured response를 사용한다.

### 4.3 Product Catalog

상품에는 최소 다음 정보가 존재한다.

- `product_id`
- `sku`
- `brand`
- `name`
- `category`
- `image_url`
- `retail_price_krw`
- 환급 계산에 필요한 최소 metadata

MVP Catalog는 시연용으로 선정한 소수 상품을 대상으로 한다.

### 4.4 Pricing

인식된 상품에 대해 다음 정보를 반환한다.

- 국내 정가
- 예상 환급액
- 예상 환급 적용가
- 자국 통화 환산가
- 즉시환급 가능 여부

정확한 환급 규정 및 환율 데이터가 확정되기 전까지는 Mock/Configured Provider를 사용할 수 있어야 한다.

사용자 UI에는 실제 확정 금액이 아닌 경우 `estimated` 의미가 유지되어야 한다.

### 4.5 Shopping Review

쇼핑 종료 후 세션 내 상품을 다음 상태로 분류할 수 있다.

- 구매 완료
- 미구매 관심
- 선택하지 않음

영수증 자동 인식이 없어도 수동 선택만으로 전체 MVP가 동작해야 한다.

### 4.6 Travel Plan

사용자는 최소 다음 정보를 세션에 연결할 수 있다.

- 출국 공항
- 항공편
- 공항 도착 예정 시간

### 4.7 Refund Checklist

Travel Plan과 구매 이력을 바탕으로 rule-based 체크리스트를 반환한다.

실제 환급 신청을 수행하지 않는다.

### 4.8 Airport Recommendation

구매 및 관심 이력을 서로 다르게 활용한다.

- `PURCHASED` → 동일 브랜드의 다른 카테고리 등 cross-sell
- `INTERESTED` → 매장에서 구매하지 않은 상품 또는 연관 상품 reminder

출국 공항에 등록된 추천 후보만 필터링할 수 있어야 한다.

## 5. P1 기능

P0 완료 후 시간이 남는 경우 구현한다.

- 영수증 이미지 기반 구매 후보 추출
- 실시간 환율 Provider
- 검증된 실제 환급 규칙 Provider
- 공항 위치 자동 감지와 연결할 API
- 실제 공항/면세점 Catalog 연동
- 추천 고도화

## 6. 명시적 제외 범위

- 결제
- 실제 세금 환급 신청 및 승인
- Web Frontend
- SSE / WebSocket 기반 UI 전달
- OpenCLIP
- pgvector
- 자체 GPU inference server
- Eye Tracking
- Hand Tracking
- 사용자 인증

## 7. MVP 성공 기준

다음 흐름이 한 번에 동작하면 P0 MVP를 완료한 것으로 본다.

```text
Android 앱에서 세션 시작
→ 관심 조건을 만족한 MCM 상품 crop 전송
→ OpenAI 기반 상품 식별
→ 상품 DB 매칭
→ 정가/예상 환급가/CNY 환산가/즉시환급 여부 반환
→ 세션 상품 목록에 중복 없이 저장
→ 쇼핑 종료
→ 구매/관심 상품 선택
→ 출국 공항/항공편/도착시간 저장
→ 체크리스트 반환
→ 구매/관심 상태에 따른 공항 추천 반환
```

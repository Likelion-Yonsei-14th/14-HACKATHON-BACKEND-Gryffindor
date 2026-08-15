# Recognition

## 1. 목적

Android 앱이 관심 행동 조건을 만족했다고 판단한 **단일 제품 중심 crop 이미지**를 받아 MVP Catalog 내 상품을 식별한다.

본 Backend는 object detector가 아니다.

```text
Android
Frame
→ Object Detection / Tracking
→ 중앙/점유율/dwell gating
→ Crop

Backend
Crop
→ OpenAI Recognition
→ product_id
```

## 2. 기존 방식에서 변경된 점

사용하지 않는다.

- OpenCLIP
- local image embedding
- pgvector
- cosine similarity threshold
- GPU / MPS / Torch runtime

OpenAI의 image input을 사용하는 모델 호출로 교체한다.

## 3. MVP Recognition Strategy

MVP는 상품 수가 적은 curated catalog를 전제로 한다.

OpenAI 요청에는 다음을 제공한다.

1. 사용자 camera crop
2. 허용된 상품 ID 목록
3. 각 상품의 최소 식별 metadata
4. 필요한 경우 reference image

상품 수가 작을 때는 query image와 여러 reference image를 하나의 요청에 포함할 수 있다.
`RecognitionCandidate.reference_image_url`이 있으면 Provider는 상품 ID label과 reference
image를 함께 전달한다. 실제 API 흐름에서는 Catalog의 `Product.image_url`을 사용하고,
local smoke test에서는 fixture JPEG을 Base64 data URL로 변환해 같은 필드에 제공한다.

상품 수가 크게 증가하면 이 방식은 비용과 latency가 증가하므로 production-scale retrieval은 별도 설계 대상이다.

## 4. Structured Result

모델 응답은 다음 schema로 제한한다.

```text
status: MATCHED | AMBIGUOUS | UNKNOWN
product_id: string | null
candidate_product_ids: string[]
```

규칙:

- `MATCHED`: 하나의 상품만 충분히 식별 가능
- `AMBIGUOUS`: 2개 이상의 후보를 구분하기 어려움
- `UNKNOWN`: Catalog에 없는 것으로 판단되거나 식별 불가

모델이 생성한 임의의 상품명은 DB key로 사용하지 않는다.

## 5. Product ID Validation

OpenAI가 반환한 `product_id`는 반드시 현재 Catalog에 존재하는지 서버에서 재검증한다.

```text
OpenAI result
→ schema validation
→ product_id allowlist validation
→ ProductRepository lookup
```

Catalog에 없는 ID는 `UNKNOWN`으로 처리한다.

## 6. Provider Interface

```python
class RecognitionProvider(Protocol):
    async def recognize(
        self,
        image_bytes: bytes,
        candidates: list[RecognitionCandidate],
    ) -> RecognitionDecision:
        ...
```

`RecognitionCandidate`의 `reference_image_url`은 optional 내부 필드며 `/api/v1` DTO에 노출하지
않는다.

구현:

```text
MockRecognitionProvider
OpenAIRecognitionProvider
```

## 7. Mock Mode

UI/Backend 병렬 작업을 위해 Mock Provider를 반드시 제공한다.

권장 방식:

- request form의 debug header 또는 fixture filename으로 deterministic product를 반환
- production 환경에서 debug override 비활성화

Mock 결과도 실제 Provider와 동일한 `RecognitionDecision` DTO를 사용한다.

## 8. API 호출 정책

- 앱의 모든 frame을 서버/OpenAI로 보내지 않는다.
- 앱에서 관심 조건을 통과한 crop만 전송한다.
- 동일 object가 지속되는 동안 과도한 반복 요청을 하지 않도록 앱에서 cooldown을 둔다.
- 서버에서도 짧은 시간 내 동일 session/product 반복 결과를 중복 row로 저장하지 않는다.

## 9. 이미지 처리

Backend에서 허용할 최소 validation:

- JPEG / PNG
- 최대 파일 크기 제한
- decode 가능한 이미지인지 확인
- 필요 시 최대 dimension으로 resize

원본 영상은 P0에서 저장하지 않는다.

## 10. 환경 변수

```text
OPENAI_API_KEY=
OPENAI_VISION_MODEL=
RECOGNITION_PROVIDER=mock|openai
RECOGNITION_MAX_IMAGE_BYTES=
RECOGNITION_MAX_CANDIDATES=
```

## 11. 완료 기준

- Mock Provider로 API contract 검증 가능
- 실제 상품 crop을 보내 OpenAI Provider가 Catalog의 product_id를 반환
- 로컬 reference fixture와 별도 촬영 query로 `MATCHED` 검증
- Catalog 밖 이미지에서 UNKNOWN 처리 가능
- 유사 상품 두 개를 구분하지 못할 때 AMBIGUOUS 처리 가능
- product_id가 DB에 존재하는지 서버 재검증
- 일반 테스트는 OpenAI 호출 없이 통과

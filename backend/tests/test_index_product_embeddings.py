from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from app.repositories.product_embeddings import ProductImageEmbedding
from app.scripts import index_product_embeddings as index_script


def test_defaults_target_final_recognition_products() -> None:
    assert index_script.DEFAULT_REFERENCE_DIR == (
        Path(index_script.__file__).resolve().parents[2] / "data" / "recognition_refs"
    )
    assert index_script.DEFAULT_PRODUCT_IDS == (
        "diptyque_leau_papier_100_001",
        "dashu_aqua_dive_50_001",
        "anillo_fragrance_of_life_10_001",
        "hatchingroom_wavy_bag_mini_nylon_001",
        "zara_leather_tote_001",
        "vivienne_westwood_wallet_5115002ew_001",
        "dior_saddle_bloom_card_wallet_s5611ctzq_m928_001",
        "dior_beauty_velvet_pouch_black_001",
    )


@pytest.mark.parametrize(
    ("create_product_directory", "expected_reason"),
    [
        (False, "Reference directory not found"),
        (True, "No reference images found"),
    ],
)
def test_find_reference_images_fails_clearly_when_images_are_missing(
    tmp_path: Path,
    create_product_directory: bool,
    expected_reason: str,
) -> None:
    product_id = "missing_refs_001"
    expected_directory = tmp_path / product_id
    if create_product_directory:
        expected_directory.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        index_script.find_reference_images(tmp_path, product_id)

    message = str(exc_info.value)
    assert expected_reason in message
    assert f"product_id={product_id}" in message
    assert f"expected_directory={expected_directory}" in message


def test_product_id_override_indexes_all_images_once_in_filename_order(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    product_id = "selected_product_001"
    product_directory = tmp_path / product_id
    product_directory.mkdir()
    (product_directory / "ref_02.png").write_bytes(b"second")
    (product_directory / "ref_01.jpg").write_bytes(b"first")
    (product_directory / "notes.txt").write_text("ignored")

    embedded_image_bytes: list[bytes] = []
    looked_up_product_ids: list[str] = []
    replace_calls: list[tuple[str, list[ProductImageEmbedding]]] = []

    class StaticEmbedder:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def embed_sync(self, image_bytes: bytes) -> list[float]:
            embedded_image_bytes.append(image_bytes)
            return [float(len(embedded_image_bytes))] * 512

    @dataclass
    class TestProduct:
        product_id: str

    class ScriptedProductRepository:
        def __init__(self, _db: object) -> None:
            pass

        def get_by_product_id(self, requested_product_id: str) -> TestProduct:
            looked_up_product_ids.append(requested_product_id)
            return TestProduct(product_id=requested_product_id)

    class RecordingEmbeddingRepository:
        def __init__(self, _db: object) -> None:
            pass

        def replace_product(
            self,
            *,
            product_id: str,
            image_embeddings: Sequence[ProductImageEmbedding],
        ) -> int:
            captured_embeddings = list(image_embeddings)
            replace_calls.append((product_id, captured_embeddings))
            return len(captured_embeddings)

    @contextmanager
    def test_session_factory() -> Generator[object, None, None]:
        yield object()

    monkeypatch.setattr(index_script, "OpenCLIPImageEmbedder", StaticEmbedder)
    monkeypatch.setattr(index_script, "ProductRepository", ScriptedProductRepository)
    monkeypatch.setattr(index_script, "ProductEmbeddingRepository", RecordingEmbeddingRepository)
    monkeypatch.setattr(index_script, "SessionLocal", test_session_factory)

    index_script.main(
        [
            "--reference-dir",
            str(tmp_path),
            "--product-id",
            product_id,
        ]
    )

    assert looked_up_product_ids == [product_id]
    assert embedded_image_bytes == [b"first", b"second"]
    assert len(replace_calls) == 1
    replaced_product_id, image_embeddings = replace_calls[0]
    assert replaced_product_id == product_id
    assert [Path(item.source_image).name for item in image_embeddings] == [
        "ref_01.jpg",
        "ref_02.png",
    ]
    assert [item.embedding[0] for item in image_embeddings] == [1.0, 2.0]
    assert capsys.readouterr().out.strip() == (
        f"indexed product_id={product_id} images=2 dimensions=512"
    )

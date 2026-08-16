from math import isclose

from app.repositories.product_embeddings import select_best_product_matches


def test_top_two_matches_are_distinct_products_with_multiple_references() -> None:
    matches = select_best_product_matches(
        [
            ("product_a", 0.08),
            ("product_a", 0.10),
            ("product_b", 0.30),
            ("product_c", 0.40),
        ],
        limit=2,
    )

    assert [match.product_id for match in matches] == ["product_a", "product_b"]
    assert matches[0].cosine_distance == 0.08
    assert isclose(matches[0].similarity, 0.92)
    assert isclose(matches[1].similarity, 0.70)
    assert isclose(matches[0].similarity - matches[1].similarity, 0.22)

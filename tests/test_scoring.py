import pytest

from app.services.scoring import score_cases


def test_score_is_deterministic_for_partial_results():
    assert score_cases(2, 3) == 66


def test_empty_test_suite_is_rejected():
    with pytest.raises(ValueError):
        score_cases(0, 0)

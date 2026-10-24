import pytest
from app.collectors.nice import NICEAdapter
from app.models.enums import CollectionStatus, RatingType

@pytest.mark.skip(reason="Live network test for Shinyoung Securities")
def test_shinyoung_securities_nice_live():
    adapter = NICEAdapter()
    res = adapter.get_ratings(
        institution_id="INS_TEST_SHINYOUNG",
        search_name="신영증권",
        rating_type=RatingType.SENIOR_BOND.value,
        target_rating_name="회사채(선순위)"
    )
    print("\n[Shinyoung NICE Live Result]:", res)
    assert res.rating == "AA-"
    assert res.status == CollectionStatus.SUCCESS.value
    assert res.company_id == "1117045"

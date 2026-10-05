from typing import Dict
from app.collectors.base import RatingAgencyAdapter
from app.collectors.krating import KRatingAdapter
from app.collectors.kis import KISAdapter
from app.collectors.nice import NICEAdapter
from app.models.enums import AgencyCode

ADAPTERS: Dict[str, RatingAgencyAdapter] = {
    AgencyCode.KR.value: KRatingAdapter(),
    AgencyCode.KIS.value: KISAdapter(),
    AgencyCode.NICE.value: NICEAdapter(),
}

def get_adapter(agency_code: str) -> RatingAgencyAdapter:
    adapter = ADAPTERS.get(agency_code)
    if not adapter:
        raise ValueError(f"Unknown agency code: {agency_code}")
    return adapter

__all__ = [
    "RatingAgencyAdapter",
    "KRatingAdapter",
    "KISAdapter",
    "NICEAdapter",
    "ADAPTERS",
    "get_adapter"
]

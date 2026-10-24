import httpx
from bs4 import BeautifulSoup
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

test_targets = ["국민은행", "KB국민은행", "농협은행", "NH농협은행", "삼성화재", "삼성화재해상보험", "메리츠화재"]

print("=== 1. KIS SEARCH TEST ===")
with httpx.Client(timeout=10.0, headers=headers, verify=True) as client:
    client.get("https://www.kisrating.com")
    for q in test_targets:
        payload = {
            "mainSearchType": "1",
            "keyword": q,
            "searchKeyword": q,
            "searchYn": "M",
            "searchType": "1"
        }
        r = client.post("https://www.kisrating.com/ratingsSearch/corp_search.do", data=payload)
        soup = BeautifulSoup(r.text, "html.parser")
        names = []
        for a in soup.find_all("a", href=True):
            if "fnCorpDetail" in a["href"]:
                names.append(a.get_text(strip=True))
        print(f"KIS query '{q}': {names[:3]}")

print("\n=== 2. NICE SEARCH TEST ===")
with httpx.Client(timeout=10.0, headers=headers, follow_redirects=True, verify=True) as client:
    for q in test_targets:
        r = client.get(f"https://www.nicerating.com/disclosure/companySearch.do?searchText={q}")
        soup = BeautifulSoup(r.text, "html.parser")
        names = []
        for a in soup.find_all("a", href=True):
            if "goView" in a["href"]:
                names.append(a.get_text(strip=True))
        print(f"NICE query '{q}': {names[:3]}")

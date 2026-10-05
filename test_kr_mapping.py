import httpx, json, sys
sys.stdout.reconfigure(encoding='utf-8')
from app.core.database import SessionLocal
from app.models.institution import Institution

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.korearatings.com/cms/frCmnCon/index.do?MENU_ID=360'
}

with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True, verify=False) as client:
    client.get('https://www.korearatings.com/cms/frCmnCon/index.do?MENU_ID=360')
    
    # 최근 1년 공시 전체 조회
    payload = {
        'MENU_ID': '360',
        'CONTENTS_NO': '1',
        'SITE_NO': '2',
        'COMP_CD': '',
        'STDT': '2025-10-01',
        'ENDT': '2026-10-01',
        'CHNG_ONLY_YN': 'N',
        'checkAll': 'Y',
        'SVCTY_CD': ['01', '07', '02', '03', '10', '11', '05', '09', '04', '06', '08']
    }
    r = client.post('https://www.korearatings.com/ajaxf/frDisclosureSvc/getRatingDisclosureList.do', data=payload)
    d = r.json().get('data', {})
    
    # comp_name -> comp_cd 맵 생성
    kr_comp_map = {}
    for k, v in d.items():
        if isinstance(v, dict) and 'Data' in v:
            for item in v['Data']:
                nm = item.get('COMP_NM')
                abbr = item.get('COMP_ABBR_NM')
                cd = item.get('COMP_CD')
                if nm and cd: kr_comp_map[nm] = cd
                if abbr and cd: kr_comp_map[abbr] = cd

    print(f"Total KR companies mapped from disclosure: {len(kr_comp_map)}")
    
    db = SessionLocal()
    matched = 0
    institutions = db.query(Institution).all()
    for inst in institutions:
        found_cd = None
        for k in kr_comp_map:
            if inst.institution_name in k or k in inst.institution_name or inst.original_name in k:
                found_cd = kr_comp_map[k]
                break
        if found_cd:
            matched += 1
            # print(f"Matched: {inst.institution_name} -> {found_cd}")
            
    print(f"Matched out of 85 institutions: {matched} / {len(institutions)}")
    db.close()

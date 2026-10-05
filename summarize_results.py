import httpx
import sys

sys.stdout.reconfigure(encoding='utf-8')

data = httpx.get('http://127.0.0.1:8000/api/v1/ratings').json()
print('Total institutions:', len(data))

statuses = {}
changes = {}
for d in data:
    s = d['overall_status']
    c = d.get('rating_change_status')
    statuses[s] = statuses.get(s, 0) + 1
    changes[c] = changes.get(c, 0) + 1

print('Overall statuses:', statuses)
print('Rating changes:', changes)

samples = ['국민은행', 'KB라이프생명', '신한은행', '삼성생명', '교보생명', 'DB생명', 'KB손해보험', 'KB증권', '카카오뱅크', '토스뱅크']
print('\n=== Key Institution Verification ===')
for s in samples:
    match = [d for d in data if s in d['institution_name'] or s in d['original_name']]
    if match:
        m = match[0]
        inst = m['institution_name']
        fnl = m['final_rating']
        prev = m['prev_final_rating']
        chg = m['rating_change_label']
        kr = f"{m['kr_rating']}({m['kr_date']})" if m['kr_rating'] else "-"
        kis = f"{m['kis_rating']}({m['kis_date']})" if m['kis_rating'] else "-"
        nice = f"{m['nice_rating']}({m['nice_date']})" if m['nice_rating'] else "-"
        print(f"[{inst}] Final: {fnl} (전월: {prev}) | {chg}")
        print(f"   KR: {kr} | KIS: {kis} | NICE: {nice}")

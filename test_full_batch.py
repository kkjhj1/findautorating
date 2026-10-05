import httpx
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("Starting full collection for all 85 institutions...")
r = httpx.post('http://127.0.0.1:8000/api/v1/collector/run', json={'execution_type': 'MANUAL_ALL'})
print('Start response:', r.status_code, r.json())

start_t = time.time()
while time.time() - start_t < 120:
    time.sleep(2)
    s = httpx.get('http://127.0.0.1:8000/api/v1/collector/status').json()
    if not s.get('is_running'):
        print('All 85 institutions collection complete!')
        break
    p = s.get('progress', {})
    proc = p.get('processed_count', 0)
    tot = p.get('total_count', 0)
    pct = p.get('progress_percent', 0.0)
    curr = p.get('current_institution', '')
    print(f"Progress: {proc}/{tot} ({pct}%) | Current: {curr}")

# Summary results
res = httpx.get('http://127.0.0.1:8000/api/v1/ratings').json()
success_cnt = sum(1 for d in res if d['overall_status'] == 'SUCCESS')
maintain_cnt = sum(1 for d in res if d.get('rating_change_status') == 'MAINTAIN')
upgrade_cnt = sum(1 for d in res if d.get('rating_change_status') == 'UPGRADE')
downgrade_cnt = sum(1 for d in res if d.get('rating_change_status') == 'DOWNGRADE')
new_cnt = sum(1 for d in res if d.get('rating_change_status') == 'NEW')

print("\n=== Collection Results Summary ===")
print(f"Total: {len(res)}")
print(f"SUCCESS count: {success_cnt}")
print(f"Maintain: {maintain_cnt}")
print(f"Upgrade: {upgrade_cnt}")
print(f"Downgrade: {downgrade_cnt}")
print(f"New: {new_cnt}")

from app.core.database import SessionLocal
from app.models.institution import Institution
from app.models.current_rating import CurrentRating

db = SessionLocal()
ratings = db.query(CurrentRating, Institution).join(Institution, CurrentRating.institution_id == Institution.institution_id).all()

print(f"Total CurrentRatings: {len(ratings)}")
no_ratings = []
manual_checks = []
partial_ratings = []
successes = []

for cur, inst in ratings:
    kr_has = cur.kr_rating is not None
    kis_has = cur.kis_rating is not None
    nice_has = cur.nice_rating is not None
    has_count = sum([kr_has, kis_has, nice_has])

    info = {
        "id": inst.institution_id,
        "name": inst.institution_name,
        "industry": inst.industry_type,
        "type": inst.rating_type,
        "kr": cur.kr_rating,
        "kis": cur.kis_rating,
        "nice": cur.nice_rating,
        "final": cur.final_rating,
        "status": cur.overall_status
    }

    if has_count == 0:
        no_ratings.append(info)
    elif has_count < 3:
        partial_ratings.append(info)
    else:
        successes.append(info)

print(f"\n1. 3사 모두 없는 기관 (완전 무등급): {len(no_ratings)}개")
for item in no_ratings[:15]:
    print(f"   [{item['industry']}] {item['name']} ({item['id']})")

print(f"\n2. 일부 평가사만 있는 기관 (1~2곳만 존재): {len(partial_ratings)}개")
for item in partial_ratings[:15]:
    print(f"   [{item['industry']}] {item['name']} -> KR:{item['kr']}, KIS:{item['kis']}, NICE:{item['nice']} (최종:{item['final']}, {item['status']})")

print(f"\n3. 3사 모두 있는 기관: {len(successes)}개")

db.close()

from app.core.database import engine, Base
import app.models # 모든 모델을 Base에 등록

def init_database():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")

if __name__ == "__main__":
    init_database()

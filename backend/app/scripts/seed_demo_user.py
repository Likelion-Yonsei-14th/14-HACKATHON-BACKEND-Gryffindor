from sqlalchemy.orm import Session

from app.constants import DEMO_USER_ID, DEMO_USER_NAME
from app.db.session import SessionLocal
from app.models.personalization import User


def seed_demo_user(db: Session) -> User:
    user = db.get(User, DEMO_USER_ID)
    if user is None:
        user = User(id=DEMO_USER_ID, name=DEMO_USER_NAME)
        db.add(user)
    else:
        user.name = DEMO_USER_NAME
    db.commit()
    return user


def main() -> None:
    with SessionLocal() as db:
        user = seed_demo_user(db)
    print(f"Seeded demo user {user.id}.")


if __name__ == "__main__":
    main()

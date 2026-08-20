from sqlalchemy.orm import Session

from app.constants import SINGLE_USER_ID, SINGLE_USER_NAME
from app.db.session import SessionLocal
from app.models.personalization import User


def seed_single_user(db: Session) -> User:
    user = db.get(User, SINGLE_USER_ID)
    if user is None:
        user = User(id=SINGLE_USER_ID, name=SINGLE_USER_NAME)
        db.add(user)
    else:
        user.name = SINGLE_USER_NAME
    db.commit()
    return user


def main() -> None:
    with SessionLocal() as db:
        user = seed_single_user(db)
    print(f"Seeded single user {user.id}.")


if __name__ == "__main__":
    main()

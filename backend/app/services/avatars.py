from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Avatar


DEFAULT_AVATARS = [
    ("cat", "🐱", "Cat"),
    ("dog", "🐶", "Dog"),
    ("fox", "🦊", "Fox"),
    ("panda", "🐼", "Panda"),
    ("bear", "🐻", "Bear"),
    ("koala", "🐨", "Koala"),
    ("tiger", "🐯", "Tiger"),
    ("lion", "🦁", "Lion"),
    ("unicorn", "🦄", "Unicorn"),
    ("whale", "🐳", "Whale"),
    ("dolphin", "🐬", "Dolphin"),
    ("owl", "🦉", "Owl"),
    ("penguin", "🐧", "Penguin"),
    ("frog", "🐸", "Frog"),
    ("hamster", "🐹", "Hamster"),
    ("robot", "🤖", "Robot"),
    ("laptop", "💻", "Laptop"),
    ("keyboard", "⌨️", "Keyboard"),
    ("brain", "🧠", "Brain"),
    ("book", "📘", "Book"),
    ("microscope", "🔬", "Microscope"),
    ("test-tube", "🧪", "Test Tube"),
    ("rocket", "🚀", "Rocket"),
    ("satellite", "🛰️", "Satellite"),
    ("spark", "✨", "Spark"),
    ("crystal-ball", "🔮", "Crystal Ball"),
    ("chart", "📈", "Chart"),
    ("medal", "🏅", "Medal"),
    ("compass", "🧭", "Compass"),
    ("puzzle", "🧩", "Puzzle"),
    ("gear", "⚙️", "Gear"),
    ("seedling", "🌱", "Seedling"),
]


def ensure_default_avatars(db: Session) -> None:
    existing = set(db.scalars(select(Avatar.id)).all())
    for avatar_id, emoji, label in DEFAULT_AVATARS:
        if avatar_id not in existing:
            db.add(Avatar(id=avatar_id, emoji=emoji, label=label))
    db.commit()


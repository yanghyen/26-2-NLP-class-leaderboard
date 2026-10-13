from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import Avatar, CourseRoster, Participant
from app.services.registration import validate_nickname


def get_participant(db: Session, student_number: str, nickname: str, emoji: str) -> Participant:
    # Match the roster's existing rule: trim surrounding whitespace only.
    roster = db.scalar(select(CourseRoster).where(CourseRoster.student_number == student_number.strip()))
    if roster is None:
        raise ValueError("수강생 명단에서 학번을 확인할 수 없습니다.")
    participant = db.scalar(select(Participant).where(Participant.roster_entry_id == roster.id))
    if participant:
        return participant
    nickname = validate_nickname(nickname)
    if not db.scalar(select(Avatar).where(Avatar.emoji == emoji, Avatar.is_active.is_(True))):
        raise ValueError("선택할 수 없는 이모지입니다.")
    participant = Participant(roster_entry_id=roster.id, nickname=nickname, emoji=emoji)
    try:
        with db.begin_nested():
            db.add(participant)
            db.flush()
    except IntegrityError:
        participant = db.scalar(select(Participant).where(Participant.roster_entry_id == roster.id))
        if participant is None:
            raise
    db.commit()
    return participant

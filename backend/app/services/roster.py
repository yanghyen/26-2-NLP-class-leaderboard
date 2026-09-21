import csv
from io import StringIO

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import CourseRoster
from app.services.registration import normalize_name


REQUIRED_COLUMNS = {"student_number", "real_name"}


def parse_roster_csv(content: str) -> list[dict[str, str | None]]:
    reader = csv.DictReader(StringIO(content))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise ValueError("CSV에는 student_number, real_name 컬럼이 필요합니다.")
    rows: list[dict[str, str | None]] = []
    for line_number, row in enumerate(reader, start=2):
        student_number = (row.get("student_number") or "").strip()
        real_name = normalize_name(row.get("real_name") or "")
        section = (row.get("section") or "").strip() or None
        if not student_number or not real_name:
            raise ValueError(f"{line_number}행의 student_number 또는 real_name이 비어 있습니다.")
        rows.append({"student_number": student_number, "real_name": real_name, "section": section})
    return rows


def upsert_roster_rows(db: Session, rows: list[dict[str, str | None]]) -> int:
    count = 0
    for row in rows:
        existing = db.query(CourseRoster).filter_by(student_number=row["student_number"]).one_or_none()
        if existing:
            existing.real_name = str(row["real_name"])
            existing.section = row["section"]
        else:
            db.add(CourseRoster(**row))
        count += 1
    db.commit()
    return count


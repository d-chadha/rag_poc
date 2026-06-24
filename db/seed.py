"""
db/seed.py
----------
Seeds the NEXUS employees table with 500 mock rows using Faker.
CITIES must match the city_tag values ingested into Chroma.

Run standalone:
    python db/seed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from sqlalchemy.orm import Session

from config.settings import CITIES, DEPARTMENTS
from db.models import Base, Employee
from db.session_factory import get_engine


def seed_employees(n: int = 500, clear_first: bool = True) -> int:
    """
    Seed *n* employee rows.  Returns the number of rows inserted.
    If *clear_first* is True, truncates the table before inserting.
    """
    fake = Faker()
    engine = get_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        if clear_first:
            session.query(Employee).delete()
            session.commit()

        employees = []
        for _ in range(n):
            employees.append(
                Employee(
                    employee_name   = fake.name(),
                    age             = fake.random_int(min=22, max=65),
                    department      = fake.random_element(DEPARTMENTS),
                    office_location = fake.random_element(CITIES),
                )
            )

        session.bulk_save_objects(employees)
        session.commit()

    print(f"Seeded {n} employees across {len(CITIES)} cities.")
    return n


if __name__ == "__main__":
    seed_employees(500)

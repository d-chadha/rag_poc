"""
db/models.py
------------
SQLAlchemy ORM model for the NEXUS employees table.
office_location is the semantic bridge — must exactly match city_tag values in Chroma.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Employee(Base):
    __tablename__ = "employees"

    employee_id     = Column(Integer, primary_key=True, autoincrement=True)
    employee_name   = Column(String(100), nullable=False)
    age             = Column(Integer, nullable=False)
    department      = Column(String(100), nullable=False)
    office_location = Column(String(100), nullable=False)
    # office_location MUST match city_tag values in Chroma weather collection

    def to_dict(self) -> dict:
        return {
            "employee_id":     self.employee_id,
            "employee_name":   self.employee_name,
            "age":             self.age,
            "department":      self.department,
            "office_location": self.office_location,
        }

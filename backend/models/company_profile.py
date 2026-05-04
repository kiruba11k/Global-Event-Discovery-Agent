"""
CompanyProfile — stores optional company context for richer event matching.
Includes extracted text from uploaded PDF deck.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, DateTime, Integer
from models.event import Base  # reuse same Base


class CompanyProfileORM(Base):
    __tablename__ = "company_profiles"

    id              = Column(String, primary_key=True)
    company_name    = Column(String, default="")
    founded_year    = Column(String, default="")
    location        = Column(String, default="")
    what_we_do      = Column(Text, default="")
    what_we_need    = Column(Text, default="")
    deck_text       = Column(Text, default="")   # extracted from PDF
    deck_filename   = Column(String, default="")
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CompanyProfileCreate(BaseModel):
    company_name: str = ""
    founded_year: str = ""
    location: str = ""
    what_we_do: str = ""
    what_we_need: str = ""


class CompanyProfileRead(CompanyProfileCreate):
    id: str
    deck_filename: str = ""
    created_at: datetime

    class Config:
        from_attributes = True

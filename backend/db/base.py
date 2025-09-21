"""SQLAlchemy declarative base definition."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for ORM models."""

    pass


__all__ = ["Base"]

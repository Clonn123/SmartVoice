"""Repository package.

This package provides a persistence abstraction layer (repository pattern).
Currently it contains a file-based implementation used as the default
storage backend. Later we will add a SQLAlchemy-based implementation and
Alembic migrations here.
"""

from .file_repository import FileCallResultRepository

__all__ = ["FileCallResultRepository"]

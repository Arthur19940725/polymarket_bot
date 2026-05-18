"""Shared pytest fixtures."""
import pytest
import tempfile
import os


@pytest.fixture
def tmp_db_path(tmp_path):
    """Temporary SQLite path that is auto-cleaned."""
    return str(tmp_path / "test.sqlite")


@pytest.fixture
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), "tests", "fixtures")

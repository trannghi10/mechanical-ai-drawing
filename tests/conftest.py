"""Unit tests use isolated storage/config, never the user's live CAD backend."""
import pytest


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    # Individual transport tests select/mock their own engine. Live AutoCAD
    # workflows are separate scripts, so changing .env cannot invoke it here.
    monkeypatch.setenv('CAD_DWG_BACKEND','oda')
    monkeypatch.setenv('CAD_READ_BACKEND','oda')

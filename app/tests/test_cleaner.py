from pathlib import Path

import pytest

from server.cleaner import CleanError, clean_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "encrypted-with-images.pdf"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture PDF missing")
def test_clean_encrypted(tmp_path):
    dest = tmp_path / "out.pdf"
    clean_pdf(FIXTURE, dest, password="")
    data = dest.read_bytes()
    assert data.startswith(b"%PDF")
    assert dest.stat().st_size > 0


def test_clean_missing_qpdf(tmp_path, monkeypatch):
    from server import cleaner

    monkeypatch.setattr(cleaner, "QPDF_BIN", "qpdf-not-installed-xyz")
    with pytest.raises(CleanError):
        clean_pdf(tmp_path / "nope.pdf", tmp_path / "out.pdf")

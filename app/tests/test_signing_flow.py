from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from server.cleaner import clean_pdf
from server.jobs import Job
from server.signing import complete_signature, prepare_signature

FIXTURE = Path(__file__).parent / "fixtures" / "encrypted-with-images.pdf"


def _tiny_pdf() -> bytes:
    return FIXTURE.read_bytes() if FIXTURE.exists() else b"%PDF-1.4\n%\ntrailer<</Size 0>>\n%%EOF\n"


def _issue_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PDF Cleaner Test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    return key, pem


def test_prepare_complete_software_key(tmp_path):
    key, pem = _issue_cert()
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    original = job_dir / "original.pdf"
    original.write_bytes(_tiny_pdf())
    cleaned = job_dir / "cleaned.pdf"
    clean_pdf(original, cleaned, password="")
    job = Job(id="t", created=0, dir=job_dir, original=original, cleaned=cleaned)
    info = prepare_signature(job, pem, box=(50, 50, 200, 100), page=0)
    assert len(info["digest_sha256"]) == 64
    tbs = bytes.fromhex(info["signed_attrs_der"])
    signature = key.sign(tbs, padding.PKCS1v15(), hashes.SHA256())
    out = complete_signature(job, signature)
    assert out.exists()
    assert b"%PDF" in out.read_bytes()[:8]


def test_api_upload_clean(tmp_path, monkeypatch):
    from server import config, main
    from server.jobs import JobStore

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    main.store.__dict__.update(JobStore().__dict__) if False else None
    from server import jobs as jobs_mod

    jobs_mod.store = JobStore()
    jobs_mod.store.__init__()
    # re-bind
    import server.main as main_mod

    main_mod.store = jobs_mod.store
    client = TestClient(main_mod.app)
    fixture = Path(__file__).parent / "fixtures" / "encrypted-with-images.pdf"
    if not fixture.exists():
        data = _tiny_pdf()
        name = "tiny.pdf"
    else:
        data = fixture.read_bytes()
        name = "encrypted-with-images.pdf"
    res = client.post("/api/upload", files={"pdf": (name, data, "application/pdf")})
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]
    res = client.post("/api/clean", json={"job_id": job_id, "password": ""})
    assert res.status_code == 200, res.text
    dl = client.get(f"/api/download/{job_id}")
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"

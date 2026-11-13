from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .cleaner import CleanError, clean_pdf
from .jobs import store
from .signing import SignError, complete_signature, prepare_signature

STATIC = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="PDF Cleaner", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CleanBody(BaseModel):
    job_id: str
    password: str = ""


class PrepareBody(BaseModel):
    job_id: str
    certificate_pem: str
    box: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    page: int = 0
    field_name: str = "Sig1"


class CompleteBody(BaseModel):
    job_id: str
    signature_hex: str


def _job(job_id: str):
    try:
        return store.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "Unknown job") from exc


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/upload")
async def upload(pdf: UploadFile = File(...)):
    data = await pdf.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    if data[:4] != b"%PDF" and b"%PDF" not in data[:1024]:
        raise HTTPException(400, "Not a PDF")
    job = store.create(pdf.filename or "upload.pdf", data)
    return {"job_id": job.id, "status": job.status, "filename": job.extra.get("filename")}


@app.post("/api/clean")
def clean(body: CleanBody):
    job = _job(body.job_id)
    dest = job.dir / "cleaned.pdf"
    try:
        clean_pdf(job.original, dest, body.password)
    except CleanError as exc:
        job.status = "error"
        job.error = str(exc)
        raise HTTPException(400, str(exc)) from exc
    job.cleaned = dest
    job.status = "cleaned"
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = _job(job_id)
    return {
        "job_id": job.id,
        "status": job.status,
        "error": job.error,
        "filename": job.extra.get("filename"),
        "has_cleaned": job.cleaned is not None,
        "has_signed": job.signed is not None,
        "prepared": job.status == "prepared",
        "digest_sha256": None
        if "signed_attrs" not in job.extra
        else hashlib.sha256(job.extra["signed_attrs"].dump()).hexdigest(),
        "placeholder_len": job.extra.get("placeholder_len"),
    }


@app.post("/api/sign/prepare")
def sign_prepare(body: PrepareBody):
    job = _job(body.job_id)
    box = tuple(body.box) if body.box else None
    try:
        info = prepare_signature(
            job,
            body.certificate_pem.encode("utf-8"),
            box=box,
            page=body.page,
            field_name=body.field_name,
        )
    except SignError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"prepare failed: {exc}") from exc
    return {"job_id": job.id, "status": job.status, **info}


@app.post("/api/sign/complete")
def sign_complete(body: CompleteBody):
    job = _job(body.job_id)
    try:
        sig = bytes.fromhex(body.signature_hex)
        complete_signature(job, sig)
    except SignError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"complete failed: {exc}") from exc
    return {"job_id": job.id, "status": job.status}


@app.get("/api/download/{job_id}")
def download(job_id: str):
    job = _job(job_id)
    path = job.signed or job.cleaned or job.original
    name = job.extra.get("filename", "document.pdf")
    if job.signed:
        name = name.replace(".pdf", "") + "-signed.pdf"
    elif job.cleaned:
        name = name.replace(".pdf", "") + "-cleaned.pdf"
    return FileResponse(path, media_type="application/pdf", filename=name)


@app.get("/api/preview/{job_id}")
def preview(job_id: str):
    job = _job(job_id)
    path = job.cleaned or job.original
    return FileResponse(path, media_type="application/pdf")


if STATIC.exists():
    app.mount("/", StaticFiles(directory=str(STATIC), html=True), name="static")

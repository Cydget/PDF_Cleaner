from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Optional

from asn1crypto import x509 as asn1_x509
from cryptography import x509 as cx509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, rsa
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import fields, signers
from pyhanko.sign.signers.pdf_signer import PdfTBSDocument
from pyhanko_certvalidator.registry import SimpleCertificateStore

from .jobs import Job


class SignError(Exception):
    pass


def _placeholder_len(cert: cx509.Certificate) -> int:
    pub = cert.public_key()
    if isinstance(pub, rsa.RSAPublicKey):
        return (pub.key_size + 7) // 8
    if isinstance(pub, dsa.DSAPublicKey):
        return (pub.key_size + 7) // 8
    if isinstance(pub, ec.EllipticCurvePublicKey):
        return 72
    raise SignError("Unsupported public key type on signing certificate")


def _load_cert(pem_or_der: bytes) -> tuple[asn1_x509.Certificate, cx509.Certificate]:
    data = pem_or_der.strip()
    if b"BEGIN CERTIFICATE" in data:
        crypto_cert = cx509.load_pem_x509_certificate(data)
        der = crypto_cert.public_bytes(serialization.Encoding.DER)
    else:
        crypto_cert = cx509.load_der_x509_certificate(data)
        der = data
    return asn1_x509.Certificate.load(der), crypto_cert


def prepare_signature(
    job: Job,
    cert_pem: bytes,
    box: Optional[tuple[int, int, int, int]] = None,
    page: int = 0,
    field_name: str = "Sig1",
) -> dict:
    src = job.cleaned or job.original
    if not src or not src.exists():
        raise SignError("No PDF to sign; clean or upload first")

    asn1_cert, crypto_cert = _load_cert(cert_pem)
    registry = SimpleCertificateStore()
    registry.register(asn1_cert)
    placeholder = signers.ExternalSigner(
        signing_cert=asn1_cert,
        cert_registry=registry,
        signature_value=bytes(_placeholder_len(crypto_cert)),
    )
    meta = signers.PdfSignatureMetadata(
        field_name=field_name,
        subfilter=fields.SigSeedSubFilter.PADES,
        md_algorithm="sha256",
    )
    new_field_spec = None
    if box is not None:
        new_field_spec = fields.SigFieldSpec(
            sig_field_name=field_name,
            on_page=page,
            box=box,
        )

    pdf_bytes = src.read_bytes()

    async def _prep() -> tuple:
        w = IncrementalPdfFileWriter(BytesIO(pdf_bytes))
        pdf_signer = signers.PdfSigner(
            meta,
            signer=placeholder,
            new_field_spec=new_field_spec,
        )
        prep_digest, tbs_document, output_handle = await pdf_signer.async_digest_doc_for_signing(w)
        signed_attrs = await placeholder.signed_attrs(
            prep_digest.document_digest, "sha256", use_pades=True
        )
        return prep_digest, tbs_document, output_handle, signed_attrs

    prep_digest, tbs_document, output_handle, signed_attrs = asyncio.run(_prep())

    prepared_path = job.dir / "prepared.pdf"
    if hasattr(output_handle, "getvalue"):
        raw = output_handle.getvalue()
    else:
        output_handle.seek(0)
        raw = output_handle.read()
    prepared_path.write_bytes(raw)
    job.prepared = prepared_path
    job.status = "prepared"
    tbs = signed_attrs.dump()
    digest = hashlib.sha256(tbs).digest()
    job.extra["prep_digest"] = prep_digest
    job.extra["signed_attrs"] = signed_attrs
    job.extra["psi"] = getattr(tbs_document, "post_sign_instructions", None)
    job.extra["output_bytes"] = raw
    job.extra["asn1_cert"] = asn1_cert
    job.extra["placeholder_len"] = _placeholder_len(crypto_cert)
    return {
        "algorithm": "sha256",
        "signed_attrs_der": tbs.hex(),
        "digest_sha256": digest.hex(),
        "placeholder_len": job.extra["placeholder_len"],
        "field_name": field_name,
    }


def complete_signature(job: Job, signature_value: bytes) -> Path:
    if "prep_digest" not in job.extra:
        raise SignError("Call /api/sign/prepare first")
    expected = job.extra["placeholder_len"]
    if len(signature_value) > expected:
        raise SignError(
            f"Signature is {len(signature_value)} bytes; placeholder reserved {expected}"
        )
    signature_value = signature_value.ljust(expected, b"\x00")

    asn1_cert = job.extra["asn1_cert"]
    registry = SimpleCertificateStore()
    registry.register(asn1_cert)
    real = signers.ExternalSigner(
        signing_cert=asn1_cert,
        cert_registry=registry,
        signature_value=signature_value,
    )
    signed_attrs = job.extra["signed_attrs"]
    output = BytesIO(job.extra["output_bytes"])

    async def _finish() -> None:
        if hasattr(real, "async_sign_prescribed_attributes"):
            sig_cms = await real.async_sign_prescribed_attributes(
                "sha256", signed_attrs=signed_attrs
            )
        else:
            sig_cms = real.sign_prescribed_attributes("sha256", signed_attrs=signed_attrs)
            if asyncio.iscoroutine(sig_cms):
                sig_cms = await sig_cms
        await PdfTBSDocument.async_finish_signing(
            output,
            prepared_digest=job.extra["prep_digest"],
            signature_cms=sig_cms,
            post_sign_instr=job.extra.get("psi"),
        )

    asyncio.run(_finish())
    dest = job.dir / "signed.pdf"
    dest.write_bytes(output.getvalue())
    job.signed = dest
    job.status = "signed"
    return dest

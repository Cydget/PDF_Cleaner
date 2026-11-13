#!/usr/bin/env python3
"""Windows-first PKCS#11 helper for PDF Cleaner.

Pulls prepare/complete from a remote API and signs with OpenSC (or another
PKCS#11 module). PIN is prompted locally and never sent to the server.

Typical OpenSC DLL:
  C:\\Program Files\\OpenSC Project\\OpenSC\\pkcs11\\opensc-pkcs11.dll
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
from pathlib import Path

import httpx

DEFAULT_MODULE = r"C:\Program Files\OpenSC Project\OpenSC\pkcs11\opensc-pkcs11.dll"


def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pem_from_der(der: bytes) -> str:
    b64 = base64.encodebytes(der).decode("ascii")
    return "-----BEGIN CERTIFICATE-----\n" + b64 + "-----END CERTIFICATE-----\n"


def run(api: str, job_id: str, module: str, pin: str, cert_label: str | None, box: list[int] | None) -> None:
    from pkcs11 import Attribute, Mechanism, ObjectClass, lib

    api = api.rstrip("/")
    pkcs11 = lib(module)
    slots = pkcs11.get_slots(token_present=True)
    if not slots:
        raise SystemExit("No PKCS#11 token present. Install OpenSC and insert the card.")
    token = slots[0].get_token()
    with token.open(user_pin=pin) as session:
        certs = list(session.get_objects({ObjectClass.CERTIFICATE}))
        if cert_label:
            certs = [c for c in certs if c[Attribute.LABEL] == cert_label]
        if not certs:
            raise SystemExit("No certificate on the token (check --cert-label).")
        pem = pem_from_der(bytes(certs[0][Attribute.VALUE]))
        body = {"job_id": job_id, "certificate_pem": pem, "field_name": "Sig1"}
        if box:
            body["box"] = box
        with httpx.Client(timeout=60.0) as client:
            prep = client.post(f"{api}/api/sign/prepare", json=body)
            if prep.status_code >= 400:
                raise SystemExit(f"prepare failed: {prep.text}")
            info = prep.json()
            digest = bytes.fromhex(info["digest_sha256"])
            keys = list(session.get_objects({ObjectClass.PRIVATE_KEY}))
            if not keys:
                raise SystemExit("No private key on the token.")
            signature = bytes(keys[0].sign(digest, mechanism=Mechanism.RSA_PKCS))
            complete = client.post(
                f"{api}/api/sign/complete",
                json={"job_id": job_id, "signature_hex": signature.hex()},
            )
            if complete.status_code >= 400:
                raise SystemExit(f"complete failed: {complete.text}")
            print("signed:", complete.json())
            print(f"Download: {api}/api/download/{job_id}")


def main() -> None:
    p = argparse.ArgumentParser(description="PDF Cleaner Windows PKCS#11 helper")
    p.add_argument("--api", required=True, help="Remote API origin, e.g. https://pdf.example.com")
    p.add_argument("--job", required=True, help="Job id from the web UI")
    p.add_argument("--module", default=DEFAULT_MODULE, help="PKCS#11 module path")
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--cert-label", default=None)
    p.add_argument("--box", default=None, help="x1,y1,x2,y2 in PDF points")
    p.add_argument("--pin", default=None, help="Token PIN (omit to prompt)")
    args = p.parse_args()
    cfg = load_config(args.config)
    module = cfg.get("module", args.module)
    cert_label = args.cert_label or cfg.get("cert_label")
    pin = args.pin or cfg.get("user_pin") or getpass.getpass("Token PIN: ")
    box = [int(x) for x in args.box.split(",")] if args.box else None
    try:
        run(args.api, args.job, module, pin, cert_label, box)
    except ImportError as exc:
        raise SystemExit("pip install python-pkcs11 httpx") from exc


if __name__ == "__main__":
    main()

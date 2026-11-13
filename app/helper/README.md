# Windows PKCS#11 helper (v1)

The web UI talks to the **remote** FastAPI host. This helper runs on the Windows PC that has the USB reader. It pulls job `prepare`/`complete` from the API and signs with OpenSC. The PIN never leaves this machine.

## Install on Windows

1. Install [OpenSC for Windows](https://github.com/OpenSC/OpenSC/releases) and confirm **Smart Card** service (`SCardSvr`) is running.
2. Insert the token. `pkcs11-tool --module "C:\Program Files\OpenSC Project\OpenSC\pkcs11\opensc-pkcs11.dll" -O` should list a cert.
3. Python 3.11+ with `httpx` and `python-pkcs11`.
4. If OpenSC does not drive your token, set `module` in `helper.config.json` to the vendor PKCS#11 DLL.

## Run

In the browser, clean a PDF and copy the job id. Then:

```bat
python windows_pkcs11_helper.py --api https://YOUR-API-HOST --job JOBID
```

Optional visible signature box: `--box 50,50,250,120`.

If a vendor module is required:

```bat
python windows_pkcs11_helper.py --api https://YOUR-API-HOST --job JOBID --module "C:\Windows\System32\eTPKCS11.dll"
```

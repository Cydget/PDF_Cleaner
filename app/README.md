# PDF Cleaner

Local/remote web app: **qpdf** decrypts and strips Adobe restrictions; **pyHanko** builds a PAdES signature; a **Windows OpenSC PKCS#11 helper** signs the digest on the PC that has the USB token. The API never sees the PIN or private key.

Future Isolated Web App / Web Smart Card clients can use the same `prepare` / `complete` HTTP contract. That path is not in v1 (Windows first).

## API host (Linux/WSL is fine)

```bash
sudo apt install qpdf
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PDFCLEANER_HOST=0.0.0.0 .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8080
```

Open `http://127.0.0.1:8080`. Put TLS and auth in front before exposing beyond a trusted network.

## Windows client (priority)

See [`helper/README.md`](helper/README.md). After upload+clean, run:

```bat
python windows_pkcs11_helper.py --api http://SERVER:8080 --job JOBID
```

## Tests

```bash
cd app
.venv/bin/pytest -q
```

## GitHub

Canonical remote: `git@github.com:Cydget/PDF_Cleaner.git`. This workspace has `origin` set, but the local SSH key could not authenticate (`error in libcrypto` after chmod 600). Push from a machine where `ssh -T git@github.com` works:

```bash
cd /root/pdfcleaner   # or clone fresh
git add app README.md .gitignore   # if you also add a root README
git status
git commit -m "Add FastAPI cleaner, pyHanko prepare/complete, Windows OpenSC helper."
git push -u origin main
```

If GitHub already has commits you want to keep, `git pull origin main --allow-unrelated-histories` first, then resolve, then push. The leftover qpdf build directories are gitignored and should not be pushed.

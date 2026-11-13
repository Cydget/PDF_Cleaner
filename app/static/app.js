const statusEl = document.getElementById("status");
const jobEl = document.getElementById("jobId");
const cmdEl = document.getElementById("helperCmd");
const dl = document.getElementById("downloadLink");
const pdfCanvas = document.getElementById("pdfCanvas");
const boxCanvas = document.getElementById("boxCanvas");
const boxLabel = document.getElementById("boxLabel");
const pageLabel = document.getElementById("pageLabel");

let jobId = null;
let pdfDoc = null;
let pageNum = 1;
let box = null;
let drag = null;
let pdfjsLib = null;

function setStatus(msg) {
  statusEl.textContent = msg;
}

function helperCommand() {
  if (!jobId) {
    cmdEl.textContent = "";
    return;
  }
  const api = window.location.origin;
  cmdEl.textContent = `python windows_pkcs11_helper.py --api ${api} --job ${jobId}`;
}

async function loadPdfJs() {
  pdfjsLib = await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.min.mjs");
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.worker.min.mjs";
}

async function renderPage() {
  if (!pdfDoc) return;
  const page = await pdfDoc.getPage(pageNum);
  const viewport = page.getViewport({ scale: 1.25 });
  pdfCanvas.width = viewport.width;
  pdfCanvas.height = viewport.height;
  boxCanvas.width = viewport.width;
  boxCanvas.height = viewport.height;
  await page.render({ canvasContext: pdfCanvas.getContext("2d"), viewport }).promise;
  pageLabel.textContent = `Page ${pageNum} / ${pdfDoc.numPages}`;
  drawBox();
}

function drawBox() {
  const ctx = boxCanvas.getContext("2d");
  ctx.clearRect(0, 0, boxCanvas.width, boxCanvas.height);
  if (!box && !drag) return;
  const r = box || drag;
  ctx.strokeStyle = "#3d8bfd";
  ctx.lineWidth = 2;
  ctx.strokeRect(r.x, r.y, r.w, r.h);
}

function canvasToPdfBox(r) {
  // canvas origin top-left; PDF origin bottom-left; scale 1.25
  const scale = 1.25;
  const x1 = r.x / scale;
  const x2 = (r.x + r.w) / scale;
  const yTop = r.y / scale;
  const yBot = (r.y + r.h) / scale;
  const pageH = pdfCanvas.height / scale;
  const pdfY1 = pageH - yBot;
  const pdfY2 = pageH - yTop;
  return [
    Math.round(Math.min(x1, x2)),
    Math.round(Math.min(pdfY1, pdfY2)),
    Math.round(Math.max(x1, x2)),
    Math.round(Math.max(pdfY1, pdfY2)),
  ];
}

boxCanvas.addEventListener("mousedown", (e) => {
  const rect = boxCanvas.getBoundingClientRect();
  drag = { x: e.clientX - rect.left, y: e.clientY - rect.top, w: 0, h: 0 };
});
boxCanvas.addEventListener("mousemove", (e) => {
  if (!drag) return;
  const rect = boxCanvas.getBoundingClientRect();
  drag.w = e.clientX - rect.left - drag.x;
  drag.h = e.clientY - rect.top - drag.y;
  drawBox();
});
window.addEventListener("mouseup", () => {
  if (!drag) return;
  box = { ...drag };
  drag = null;
  const pdfBox = canvasToPdfBox(box);
  boxLabel.textContent = `Box: ${pdfBox.join(", ")}`;
  box.pdf = pdfBox;
  drawBox();
});

document.getElementById("prevPage").onclick = async () => {
  if (pdfDoc && pageNum > 1) {
    pageNum -= 1;
    await renderPage();
  }
};
document.getElementById("nextPage").onclick = async () => {
  if (pdfDoc && pageNum < pdfDoc.numPages) {
    pageNum += 1;
    await renderPage();
  }
};

document.getElementById("uploadBtn").onclick = async () => {
  const file = document.getElementById("file").files[0];
  if (!file) {
    setStatus("Choose a PDF first.");
    return;
  }
  setStatus("Uploading…");
  const fd = new FormData();
  fd.append("pdf", file);
  const up = await fetch("/api/upload", { method: "POST", body: fd });
  const upJson = await up.json();
  if (!up.ok) {
    setStatus(upJson.detail || "Upload failed");
    return;
  }
  jobId = upJson.job_id;
  jobEl.textContent = jobId;
  helperCommand();
  const clean = await fetch("/api/clean", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      password: document.getElementById("password").value,
    }),
  });
  const cleanJson = await clean.json();
  if (!clean.ok) {
    setStatus(cleanJson.detail || "Clean failed");
    return;
  }
  setStatus("Cleaned. Preview below.");
  dl.hidden = false;
  dl.href = `/api/download/${jobId}`;
  await loadPdfJs();
  const buf = await fetch(`/api/preview/${jobId}`).then((r) => r.arrayBuffer());
  pdfDoc = await pdfjsLib.getDocument({ data: buf }).promise;
  pageNum = 1;
  await renderPage();
};

document.getElementById("prepBtn").onclick = async () => {
  if (!jobId) return setStatus("Upload first.");
  const certificate_pem = document.getElementById("certPem").value;
  if (!certificate_pem.includes("BEGIN CERTIFICATE")) {
    setStatus("Paste a PEM certificate or use the Windows helper.");
    return;
  }
  const body = {
    job_id: jobId,
    certificate_pem,
    page: pageNum - 1,
    field_name: "Sig1",
  };
  if (box?.pdf) body.box = box.pdf;
  const res = await fetch("/api/sign/prepare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) {
    setStatus(json.detail || "Prepare failed");
    return;
  }
  setStatus(`Prepared. Digest SHA-256: ${json.digest_sha256}`);
};

document.getElementById("completeBtn").onclick = async () => {
  if (!jobId) return;
  const signature_hex = document.getElementById("sigHex").value.trim();
  const res = await fetch("/api/sign/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, signature_hex }),
  });
  const json = await res.json();
  if (!res.ok) {
    setStatus(json.detail || "Complete failed");
    return;
  }
  setStatus("Signed.");
  dl.hidden = false;
  dl.href = `/api/download/${jobId}`;
};

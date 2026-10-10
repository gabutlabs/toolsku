const form = document.querySelector("#compression-form");
const fileInput = document.querySelector("#pdf-file");
const uploadZone = document.querySelector("#upload-zone");
const selectedFile = document.querySelector("#selected-file");
const fileError = document.querySelector("#file-error");
const customInput = document.querySelector("#custom-size-mb");
const customError = document.querySelector("#custom-size-error");
const targetCards = [...document.querySelectorAll(".target-card")];
const jobPanel = document.querySelector("#job-panel");
const statusTitle = document.querySelector("#status-title");
const statusDescription = document.querySelector("#status-description");
const statusIcon = document.querySelector("#status-icon");
const progressIndicator = document.querySelector("#progress-indicator");
const resultPanel = document.querySelector("#result-panel");
const errorPanel = document.querySelector("#error-panel");
const compressButton = document.querySelector("#compress-button");

const MAX_UPLOAD_BYTES = 50_000_000;
const POLL_DELAY_MS = 1200;
let activeJobId = null;
let polling = false;
let lastValidCustomValue = "";

function formatSize(bytes) {
  if (bytes < 1_000_000) {
    return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  }

  return `${(bytes / 1_000_000).toFixed(2).replace(/0+$/, "").replace(/\.$/, "")} MB`;
}

function selectedTarget() {
  return document.querySelector('input[name="size_option"]:checked')?.value;
}

function setFileError(message = "") {
  fileError.textContent = message;
  fileError.hidden = !message;
  fileInput.setAttribute("aria-invalid", message ? "true" : "false");
}

function setCustomError(message = "") {
  customError.textContent = message;
  customError.hidden = !message;
  customInput.setAttribute("aria-invalid", message ? "true" : "false");
}

function showFile(file) {
  setFileError("");
  if (!file) {
    selectedFile.hidden = true;
    return;
  }

  if (!file.name.toLowerCase().endsWith(".pdf")) {
    fileInput.value = "";
    selectedFile.hidden = true;
    setFileError("Choose a PDF file to continue.");
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    fileInput.value = "";
    selectedFile.hidden = true;
    setFileError("This PDF is larger than the 50 MB upload limit.");
    return;
  }

  document.querySelector("#selected-file-name").textContent = file.name;
  document.querySelector("#selected-file-size").textContent = formatSize(file.size);
  selectedFile.hidden = false;
}

function syncTargetSelection() {
  const isCustom = selectedTarget() === "custom";
  customInput.disabled = !isCustom;
  customInput.required = isCustom;
  targetCards.forEach((card) => {
    card.classList.toggle("is-selected", card.querySelector(".btn-check").checked);
  });
  if (!isCustom) setCustomError("");
}

function setBusy(busy) {
  fileInput.disabled = busy;
  document.querySelectorAll('input[name="size_option"]').forEach((input) => {
    input.disabled = busy;
  });
  customInput.disabled = busy || selectedTarget() !== "custom";
  document.querySelector("#remove-file").disabled = busy;
  compressButton.disabled = busy;
  compressButton.textContent = busy ? "Uploading PDF…" : "Compress PDF";
}

function setStatusIcon(state) {
  const loading = state === "loading";
  const complete = state === "complete";
  statusIcon.classList.toggle("status-icon-loading", loading);
  statusIcon.classList.toggle("status-icon-failed", state === "failed");
  statusIcon.querySelector(".spinner-border").hidden = !loading;
  statusIcon.querySelector(".status-mark-complete").hidden = !complete;
  statusIcon.querySelector(".status-mark-failed").hidden = state !== "failed";
}

function showJobState(state) {
  jobPanel.hidden = false;
  form.hidden = true;
  resultPanel.hidden = true;
  errorPanel.hidden = true;
  setStatusIcon("loading");

  if (state === "queued") {
    statusTitle.textContent = "Waiting in the queue";
    statusDescription.textContent = "We’ll start as soon as a worker is available.";
    progressIndicator.hidden = false;
  } else {
    statusTitle.textContent = "Compressing your PDF";
    statusDescription.textContent = "This can take a little while for larger files.";
    progressIndicator.hidden = false;
  }
}

function showError(message, title = "We couldn’t compress this PDF.") {
  jobPanel.hidden = false;
  form.hidden = true;
  progressIndicator.hidden = true;
  resultPanel.hidden = true;
  errorPanel.hidden = false;
  setStatusIcon("failed");
  statusTitle.textContent = "Compression failed";
  statusDescription.textContent = "Choose another PDF to try again.";
  document.querySelector("#error-title").textContent = title;
  document.querySelector("#error-message").textContent = message;
}

function showResult(job) {
  progressIndicator.hidden = true;
  resultPanel.hidden = false;
  errorPanel.hidden = true;
  setStatusIcon("complete");
  statusTitle.textContent = "Compression complete";
  statusDescription.textContent = job.filename;
  document.querySelector("#result-message").textContent = job.message;
  document.querySelector("#original-size").textContent = formatSize(job.original_size);
  document.querySelector("#compressed-size").textContent = formatSize(job.output_size);
  document.querySelector("#download-button").href = job.download_url;

  const savedStat = document.querySelector("#saved-stat");
  const savedSize = document.querySelector("#saved-size");
  if (job.output_size < job.original_size) {
    const savedPercent = Math.round((1 - job.output_size / job.original_size) * 100);
    savedSize.textContent = `${savedPercent}% smaller`;
    savedStat.hidden = false;
  } else {
    savedStat.hidden = true;
  }
}

function resetForm() {
  activeJobId = null;
  polling = false;
  form.reset();
  fileInput.value = "";
  customInput.value = "";
  lastValidCustomValue = "";
  selectedFile.hidden = true;
  jobPanel.hidden = true;
  form.hidden = false;
  progressIndicator.hidden = false;
  resultPanel.hidden = true;
  errorPanel.hidden = true;
  setFileError("");
  setCustomError("");
  syncTargetSelection();
  setBusy(false);
  document.querySelector("#target-recommended").focus();
}

async function responseError(response) {
  try {
    const payload = await response.json();
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      if (detail.some((issue) => issue.loc?.includes("file") && issue.type === "missing")) {
        return "Choose a PDF file to continue.";
      }
      return detail.map((issue) => issue.msg).filter(Boolean).join(" ")
        || "We couldn’t upload this PDF. Try again.";
    }
    return "We couldn’t upload this PDF. Try again.";
  } catch {
    return "We couldn’t upload this PDF. Try again.";
  }
}

async function pollJob(jobId) {
  if (polling) return;
  polling = true;

  while (activeJobId === jobId) {
    await new Promise((resolve) => window.setTimeout(resolve, POLL_DELAY_MS));
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      if (!response.ok) throw new Error("We lost the connection to this compression job.");
      const job = await response.json();

      if (job.status === "queued") {
        showJobState("queued");
      } else if (job.status === "processing") {
        showJobState("processing");
      } else if (job.status === "completed") {
        showResult(job);
        polling = false;
        return;
      } else if (job.status === "failed") {
        const title = job.target_met === false
          ? "The size target couldn’t be reached."
          : undefined;
        showError(job.message, title);
        polling = false;
        return;
      }
    } catch (error) {
      showError(error.message || "We lost the connection to this compression job.");
      polling = false;
      return;
    }
  }

  polling = false;
}

fileInput.addEventListener("change", () => showFile(fileInput.files[0]));

document.querySelector("#remove-file").addEventListener("click", () => {
  fileInput.value = "";
  showFile(null);
});

document.querySelectorAll('input[name="size_option"]').forEach((input) => {
  input.addEventListener("change", () => {
    syncTargetSelection();
    if (input.value === "custom") customInput.focus();
  });
});

customInput.addEventListener("beforeinput", (event) => {
  if (event.data && /\D/.test(event.data)) {
    event.preventDefault();
    setCustomError("Enter a whole number. Decimal values aren’t accepted.");
  }
});

customInput.addEventListener("paste", (event) => {
  const pastedText = event.clipboardData?.getData("text") || "";
  if (/\D/.test(pastedText)) {
    event.preventDefault();
    setCustomError("Enter a whole number. Decimal values aren’t accepted.");
  }
});

customInput.addEventListener("input", () => {
  if (/\D/.test(customInput.value)) {
    customInput.value = lastValidCustomValue;
    setCustomError("Enter a whole number. Decimal values aren’t accepted.");
    return;
  }
  lastValidCustomValue = customInput.value;
  setCustomError("");
});

for (const eventName of ["dragenter", "dragover"]) {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.remove("is-dragging");
  });
}

uploadZone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  if (!file) return;

  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  showFile(file);
});

document.querySelector("#another-button").addEventListener("click", resetForm);
document.querySelector("#retry-button").addEventListener("click", resetForm);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFileError("");

  const file = fileInput.files[0];
  if (!file) {
    setFileError("Choose a PDF file to continue.");
    fileInput.focus();
    return;
  }
  if (selectedTarget() === "custom") {
    if (customError.textContent) {
      customInput.focus();
      return;
    }
    if (!customInput.value || Number(customInput.value) < 1) {
      setCustomError("Enter a whole-number target of at least 1 MB.");
      customInput.focus();
      return;
    }
  }

  const formData = new FormData(form);
  setBusy(true);
  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error(await responseError(response));
    const job = await response.json();
    activeJobId = job.id;
    showJobState("queued");
    pollJob(job.id);
  } catch (error) {
    setBusy(false);
    showError(error.message || "We couldn’t upload this PDF. Try again.");
  }
});

syncTargetSelection();

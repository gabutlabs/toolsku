const form = document.querySelector("#image-compression-form");
const fileInput = document.querySelector("#image-file");
const uploadZone = document.querySelector("#image-upload-zone");
const selectedFile = document.querySelector("#image-selected-file");
const fileError = document.querySelector("#image-file-error");
const outputFormatSelect = document.querySelector("#image-output-format");
const sourceFormatOption = outputFormatSelect.querySelector('option[value="source"]');
const formatHelp = document.querySelector("#image-format-help");
const sizeInput = document.querySelector("#image-size-kb");
const sizePreview = document.querySelector("#image-size-preview");
const sizeError = document.querySelector("#image-size-error");
const targetCards = [...document.querySelectorAll(".target-card")];
const jobPanel = document.querySelector("#image-job-panel");
const statusTitle = document.querySelector("#image-status-title");
const statusDescription = document.querySelector("#image-status-description");
const statusIcon = document.querySelector("#image-status-icon");
const progressIndicator = document.querySelector("#image-progress-indicator");
const resultPanel = document.querySelector("#image-result-panel");
const errorPanel = document.querySelector("#image-error-panel");
const compressButton = document.querySelector("#image-compress-button");
const tryWebpButton = document.querySelector("#try-webp-button");

const MAX_UPLOAD_BYTES = 50_000_000;
const MIN_TARGET_KB = 10;
const MAX_TARGET_KB = 50_000;
const POLL_DELAY_MS = 1200;
let activeJobId = null;
let polling = false;
let lastValidTarget = "";
let selectedSourceFormat = null;

function formatSize(bytes) {
  const roundedKilobytes = Math.max(1, Math.round(bytes / 1000));
  if (roundedKilobytes < 1000) return `${roundedKilobytes} KB`;

  const megabytes = (bytes / 1_000_000).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return `${megabytes} MB`;
}

function formatSizeLimit(kilobytes) {
  if (kilobytes < 1000) return `${kilobytes} KB`;

  const megabytes = (kilobytes / 1000).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return `${megabytes} MB`;
}

function syncSizePreview() {
  const kilobytes = Number(sizeInput.value);
  const showPreview = selectedTarget() === "custom" && sizeInput.value !== "";
  sizePreview.textContent = showPreview ? `Output limit: up to ${formatSizeLimit(kilobytes)}.` : "";
  sizePreview.hidden = !showPreview;
}

function selectedTarget() {
  return document.querySelector('input[name="size_option"]:checked')?.value;
}

function setFileError(message = "") {
  fileError.textContent = message;
  fileError.hidden = !message;
  fileInput.setAttribute("aria-invalid", message ? "true" : "false");
}

function formatFromFilename(filename) {
  const extension = filename.split(".").pop()?.toLowerCase();
  if (extension === "jpg" || extension === "jpeg") return "JPEG";
  if (extension === "png") return "PNG";
  if (extension === "webp") return "WebP";
  return null;
}

function syncFormatHelp() {
  const outputFormat = outputFormatSelect.value;
  if (outputFormat === "source") {
    sourceFormatOption.textContent = selectedSourceFormat
      ? `Same as uploaded (${selectedSourceFormat})`
      : "Same as uploaded image";
    formatHelp.textContent = selectedSourceFormat
      ? `Your output will stay in ${selectedSourceFormat} format.`
      : "Same as uploaded uses the format detected in your image.";
  } else if (outputFormat === "jpeg") {
    formatHelp.textContent = "Transparency, if present, will be filled with white.";
  } else if (outputFormat === "png") {
    formatHelp.textContent = "PNG keeps transparency and uses lossless compression.";
  } else {
    formatHelp.textContent = "WebP works well for sharing and smaller files.";
  }
}

function setSizeError(message = "") {
  sizeError.textContent = message;
  sizeError.hidden = !message;
  sizeInput.setAttribute("aria-invalid", message ? "true" : "false");
}

function showFile(file) {
  setFileError("");
  if (!file) {
    selectedFile.hidden = true;
    selectedSourceFormat = null;
    syncFormatHelp();
    return;
  }

  const extension = file.name.split(".").pop()?.toLowerCase();
  if (!["jpg", "jpeg", "png", "webp"].includes(extension)) {
    fileInput.value = "";
    selectedFile.hidden = true;
    selectedSourceFormat = null;
    syncFormatHelp();
    setFileError("Choose a JPG, PNG, or WebP image.");
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    fileInput.value = "";
    selectedFile.hidden = true;
    selectedSourceFormat = null;
    syncFormatHelp();
    setFileError("This image is larger than the 50 MB upload limit.");
    return;
  }

  selectedSourceFormat = formatFromFilename(file.name);
  document.querySelector("#image-file-name").textContent = file.name;
  document.querySelector("#image-file-details").textContent = `${selectedSourceFormat} · ${formatSize(file.size)}`;
  selectedFile.hidden = false;
  syncFormatHelp();
}

function syncTargetSelection() {
  const isCustom = selectedTarget() === "custom";
  sizeInput.disabled = !isCustom;
  sizeInput.required = isCustom;
  document.querySelectorAll(".size-example").forEach((button) => {
    button.disabled = !isCustom;
  });
  targetCards.forEach((card) => {
    card.classList.toggle("is-selected", card.querySelector(".btn-check").checked);
  });
  syncSizePreview();
  if (!isCustom) setSizeError("");
}

function setBusy(busy) {
  fileInput.disabled = busy;
  document.querySelectorAll('input[name="size_option"]').forEach((input) => {
    input.disabled = busy;
  });
  sizeInput.disabled = busy || selectedTarget() !== "custom";
  document.querySelectorAll(".size-example").forEach((button) => {
    button.disabled = busy || selectedTarget() !== "custom";
  });
  outputFormatSelect.disabled = busy;
  document.querySelector("#remove-image").disabled = busy;
  compressButton.disabled = busy;
  compressButton.textContent = busy ? "Uploading image…" : "Compress image";
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

function showJobState(state, queuedMessage = "") {
  jobPanel.hidden = false;
  form.hidden = true;
  resultPanel.hidden = true;
  errorPanel.hidden = true;
  setStatusIcon("loading");

  if (state === "queued") {
    statusTitle.textContent = "Waiting in the queue";
    statusDescription.textContent = queuedMessage || "We’ll start as soon as a worker is available.";
  } else {
    statusTitle.textContent = "Compressing your image";
    statusDescription.textContent = "This can take a little while for larger images.";
  }
  progressIndicator.hidden = false;
}

function showError(message, title = "We couldn’t compress this image.", canTryWebp = false) {
  jobPanel.hidden = false;
  form.hidden = true;
  progressIndicator.hidden = true;
  resultPanel.hidden = true;
  errorPanel.hidden = false;
  setStatusIcon("failed");
  statusTitle.textContent = "Compression failed";
  statusDescription.textContent = canTryWebp
    ? "Try another format or choose a different image."
    : "Choose another image to try again.";
  document.querySelector("#image-error-title").textContent = title;
  document.querySelector("#image-error-message").textContent = message;
  tryWebpButton.hidden = !canTryWebp;
}

function showResult(job) {
  progressIndicator.hidden = true;
  resultPanel.hidden = false;
  errorPanel.hidden = true;
  setStatusIcon("complete");
  statusTitle.textContent = "Compression complete";
  statusDescription.textContent = job.filename;
  document.querySelector("#image-result-message").textContent = `${job.message} Output format: ${job.output_format.toUpperCase()}.`;
  document.querySelector("#image-original-size").textContent = formatSize(job.original_size);
  document.querySelector("#image-compressed-size").textContent = formatSize(job.output_size);
  document.querySelector("#image-download-button").href = job.download_url;

  const savedStat = document.querySelector("#image-saved-stat");
  const savedSize = document.querySelector("#image-saved-size");
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
  sizeInput.value = "";
  lastValidTarget = "";
  selectedSourceFormat = null;
  selectedFile.hidden = true;
  jobPanel.hidden = true;
  form.hidden = false;
  progressIndicator.hidden = false;
  resultPanel.hidden = true;
  errorPanel.hidden = true;
  setFileError("");
  setSizeError("");
  syncFormatHelp();
  syncTargetSelection();
  setBusy(false);
  document.querySelector("#image-recommended").focus();
}

async function responseError(response) {
  try {
    const payload = await response.json();
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((issue) => issue.msg).filter(Boolean).join(" ");
    return "We couldn’t upload this image. Try again.";
  } catch {
    return "We couldn’t upload this image. Try again.";
  }
}

async function pollJob(jobId) {
  if (polling) return;
  polling = true;

  while (activeJobId === jobId) {
    await new Promise((resolve) => window.setTimeout(resolve, POLL_DELAY_MS));
    try {
      const response = await fetch(`/api/image-jobs/${jobId}`);
      if (!response.ok) throw new Error("We lost the connection to this image job.");
      const job = await response.json();

      if (job.status === "queued" || job.status === "processing") {
        showJobState(job.status, job.message);
      } else if (job.status === "completed") {
        showResult(job);
        polling = false;
        return;
      } else if (job.status === "failed") {
        const title = job.target_met === false
          ? "The size limit couldn’t be reached."
          : undefined;
        const canTryWebp = job.output_format === "png" && selectedTarget() === "custom";
        showError(job.message, title, canTryWebp);
        polling = false;
        return;
      }
    } catch (error) {
      showError(error.message || "We lost the connection to this image job.");
      polling = false;
      return;
    }
  }

  polling = false;
}

fileInput.addEventListener("change", () => showFile(fileInput.files[0]));
outputFormatSelect.addEventListener("change", syncFormatHelp);

document.querySelector("#remove-image").addEventListener("click", () => {
  fileInput.value = "";
  showFile(null);
});

document.querySelectorAll('input[name="size_option"]').forEach((input) => {
  input.addEventListener("change", () => {
    syncTargetSelection();
    if (input.value === "custom") sizeInput.focus();
  });
});

document.querySelectorAll(".size-example").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#image-custom").checked = true;
    syncTargetSelection();
    sizeInput.value = button.dataset.sizeKb;
    lastValidTarget = sizeInput.value;
    syncSizePreview();
    setSizeError("");
  });
});

sizeInput.addEventListener("beforeinput", (event) => {
  if (event.data && /\D/.test(event.data)) {
    event.preventDefault();
    setSizeError("Enter a whole number of kilobytes.");
  }
});

sizeInput.addEventListener("paste", (event) => {
  const pastedText = event.clipboardData?.getData("text") || "";
  if (/\D/.test(pastedText)) {
    event.preventDefault();
    setSizeError("Enter a whole number of kilobytes.");
  }
});

sizeInput.addEventListener("input", () => {
  if (/\D/.test(sizeInput.value)) {
    sizeInput.value = lastValidTarget;
    setSizeError("Enter a whole number of kilobytes.");
    return;
  }
  lastValidTarget = sizeInput.value;
  syncSizePreview();
  setSizeError("");
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

document.querySelector("#another-image-button").addEventListener("click", resetForm);
document.querySelector("#retry-image-button").addEventListener("click", resetForm);
tryWebpButton.addEventListener("click", () => {
  activeJobId = null;
  polling = false;
  jobPanel.hidden = true;
  form.hidden = false;
  outputFormatSelect.value = "webp";
  syncFormatHelp();
  setBusy(false);
  outputFormatSelect.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFileError("");

  const file = fileInput.files[0];
  if (!file) {
    setFileError("Choose an image file to continue.");
    fileInput.focus();
    return;
  }
  if (selectedTarget() === "custom") {
    const targetKb = Number(sizeInput.value);
    if (sizeError.textContent || !Number.isInteger(targetKb) || targetKb < MIN_TARGET_KB || targetKb > MAX_TARGET_KB) {
      setSizeError("Enter a whole-number limit from 10 to 50,000 KB.");
      sizeInput.focus();
      return;
    }
  }

  const formData = new FormData(form);
  setBusy(true);
  try {
    const response = await fetch("/api/image-jobs", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error(await responseError(response));
    const job = await response.json();
    activeJobId = job.id;
    showJobState("queued", job.message);
    pollJob(job.id);
  } catch (error) {
    setBusy(false);
    showError(error.message || "We couldn’t upload this image. Try again.");
  }
});

syncTargetSelection();

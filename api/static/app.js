const form = document.getElementById("jobForm");
const statusValue = document.getElementById("statusValue");
const jobIdEl = document.getElementById("jobId");
const queuedAt = document.getElementById("queuedAt");
const endedAt = document.getElementById("endedAt");
const downloadLink = document.getElementById("downloadLink");
const errorBox = document.getElementById("errorBox");

let pollTimer = null;

function setStatus(text, tone = "default") {
  statusValue.textContent = text;
  statusValue.style.background =
    tone === "error" ? "rgba(255, 98, 98, 0.18)" : "rgba(95, 163, 255, 0.2)";
  statusValue.style.color = tone === "error" ? "#ffc2c2" : "#cfe0ff";
}

function setDownload(url) {
  if (!url) {
    downloadLink.classList.add("disabled");
    downloadLink.setAttribute("aria-disabled", "true");
    downloadLink.textContent = "Not ready";
    downloadLink.href = "#";
    return;
  }
  downloadLink.classList.remove("disabled");
  downloadLink.removeAttribute("aria-disabled");
  downloadLink.textContent = "Download ZIP";
  downloadLink.href = url;
}

function showError(text) {
  if (!text) {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
    return;
  }
  errorBox.classList.remove("hidden");
  errorBox.textContent = text;
}

async function fetchStatus(jobId) {
  const res = await fetch(`/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Status request failed: ${res.status}`);
  }
  return res.json();
}

async function pollJob(jobId) {
  if (pollTimer) {
    clearInterval(pollTimer);
  }

  const update = async () => {
    try {
      const data = await fetchStatus(jobId);
      setStatus(data.status);
      queuedAt.textContent = data.created_at || "—";
      endedAt.textContent = data.ended_at || "—";
      showError(data.error || "");

      if (data.status === "finished") {
        setDownload(`/jobs/${jobId}/download`);
        clearInterval(pollTimer);
      } else if (data.status === "failed") {
        setDownload(null);
        setStatus("failed", "error");
        clearInterval(pollTimer);
      }
    } catch (err) {
      setStatus("error", "error");
      showError(err.message);
      clearInterval(pollTimer);
    }
  };

  await update();
  pollTimer = setInterval(update, 2000);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  setDownload(null);

  const fileInput = document.getElementById("file");
  if (!fileInput.files.length) {
    showError("Please choose a file before submitting.");
    return;
  }

  const formData = new FormData(form);
  setStatus("uploading");

  try {
    const res = await fetch("/jobs", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || "Upload failed.");
    }

    const data = await res.json();
    jobIdEl.textContent = data.job_id || "unknown";
    setStatus(data.status || "queued");
    queuedAt.textContent = "—";
    endedAt.textContent = "—";
    await pollJob(data.job_id);
  } catch (err) {
    setStatus("error", "error");
    showError(err.message);
  }
});

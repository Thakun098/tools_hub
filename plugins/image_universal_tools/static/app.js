(() => {
  "use strict";

  const base = document.body.dataset.baseUrl || "/image-tools";
  const allowedExtensions = /\.(png|jpe?g|webp|bmp|tiff?)$/i;
  const terminalStates = new Set(["completed", "failed", "cancelled"]);
  const state = {
    files: [],
    activeFile: 0,
    operation: "remove_background",
    models: [],
    selectedModelId: "balanced-isnet",
    busy: false,
    jobTimer: null,
    modelTimer: null,
    toastTimer: null,
  };

  const $ = (selector) => document.querySelector(selector);
  const elements = {
    dropZone: $("#drop-zone"),
    fileInput: $("#file-input"),
    chooseButton: $("#choose-button"),
    clearFiles: $("#clear-files"),
    selectionCount: $("#selection-count"),
    preview: $("#preview"),
    previewImage: $("#preview-image"),
    previewEmpty: $(".preview-empty"),
    selectedList: $("#selected-list"),
    tabs: [...document.querySelectorAll(".tab")],
    removePanel: $("#remove-panel"),
    convertPanel: $("#convert-panel"),
    modelOptions: $("#model-options"),
    modelTitle: $("#model-title"),
    modelDetail: $("#model-detail"),
    modelProgress: $("#model-progress"),
    modelProgressBar: $("#model-progress span"),
    modelAction: $("#model-action"),
    outputFormat: $("#output-format"),
    quality: $("#quality"),
    qualityValue: $("#quality-value"),
    transparentBackground: $("#transparent-background"),
    colorBackground: $("#color-background"),
    backgroundColor: $("#background-color"),
    alphaWarning: $("#alpha-warning"),
    startButton: $("#start-button"),
    startLabel: $("#start-button span"),
    queueBody: $("#queue-body"),
    queueCount: $("#queue-count"),
    cancelAll: $("#cancel-all"),
    toast: $("#toast"),
  };

  function showToast(message, isError = false) {
    clearTimeout(state.toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.toggle("error", isError);
    elements.toast.classList.add("show");
    state.toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 3200);
  }

  async function api(path, options = {}) {
    const response = await fetch(`${base}${path}`, options);
    let payload;
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function revokeFiles() {
    state.files.forEach((item) => URL.revokeObjectURL(item.url));
  }

  function setFiles(fileList) {
    const accepted = [...fileList].filter((file) => allowedExtensions.test(file.name));
    if (accepted.length !== fileList.length) showToast("ข้ามไฟล์ที่ไม่ใช่ PNG, JPEG, WebP, BMP หรือ TIFF", true);
    const existing = new Set(state.files.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`));
    accepted.forEach((file) => {
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (!existing.has(key) && state.files.length < 100) {
        state.files.push({ file, url: URL.createObjectURL(file) });
        existing.add(key);
      }
    });
    state.activeFile = Math.min(state.activeFile, Math.max(0, state.files.length - 1));
    renderFiles();
  }

  function renderFiles() {
    elements.selectionCount.textContent = `(${state.files.length})`;
    elements.clearFiles.disabled = state.files.length === 0 || state.busy;
    elements.selectedList.replaceChildren();
    state.files.forEach((item, index) => {
      const chip = document.createElement("div");
      chip.className = `file-chip${index === state.activeFile ? " active" : ""}`;
      const select = document.createElement("button");
      select.type = "button";
      select.textContent = item.file.name;
      select.title = item.file.name;
      select.addEventListener("click", () => { state.activeFile = index; renderFiles(); });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-file";
      remove.setAttribute("aria-label", `เอา ${item.file.name} ออกจากรายการ`);
      remove.textContent = "×";
      remove.disabled = state.busy;
      remove.addEventListener("click", () => {
        URL.revokeObjectURL(item.url);
        state.files.splice(index, 1);
        state.activeFile = Math.min(state.activeFile, Math.max(0, state.files.length - 1));
        renderFiles();
      });
      chip.append(select, remove);
      elements.selectedList.append(chip);
    });
    if (state.files.length) {
      elements.previewImage.src = state.files[state.activeFile].url;
      elements.previewImage.hidden = false;
      elements.previewEmpty.hidden = true;
    } else {
      elements.previewImage.removeAttribute("src");
      elements.previewImage.hidden = true;
      elements.previewEmpty.hidden = false;
    }
    updateStartButton();
  }

  function selectedModel() {
    return state.models.find((model) => model.id === state.selectedModelId);
  }

  function formatBytes(value) {
    if (!Number.isFinite(value)) return "—";
    if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(value < 10 * 1024 ** 2 ? 1 : 0)} MB`;
    return `${Math.round(value / 1024)} KB`;
  }

  function renderModels() {
    elements.modelOptions.replaceChildren();
    state.models.forEach((model) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `model-option${model.id === state.selectedModelId ? " active" : ""}`;
      button.setAttribute("aria-pressed", model.id === state.selectedModelId ? "true" : "false");
      const title = document.createElement("strong");
      title.textContent = model.tier;
      const description = document.createElement("span");
      description.textContent = model.name_th;
      const size = document.createElement("small");
      size.textContent = `${formatBytes(model.size_bytes)} · ${model.license}`;
      button.append(title, description, size);
      button.addEventListener("click", () => {
        state.selectedModelId = model.id;
        renderModels();
        renderModelStatus();
      });
      elements.modelOptions.append(button);
    });
    renderModelStatus();
  }

  function renderModelStatus() {
    const model = selectedModel();
    if (!model) {
      elements.modelTitle.textContent = "ไม่พบข้อมูลโมเดล";
      elements.modelDetail.textContent = "ลองโหลดหน้าใหม่อีกครั้ง";
      elements.modelAction.disabled = true;
      updateStartButton();
      return;
    }
    const status = model.download_status;
    elements.modelTitle.textContent = `${model.tier} · ${model.name_th}`;
    elements.modelProgress.hidden = status !== "downloading";
    const percent = model.size_bytes ? Math.min(100, Math.round(model.downloaded_bytes / model.size_bytes * 100)) : 0;
    elements.modelProgressBar.style.width = `${percent}%`;
    elements.modelAction.disabled = false;
    if (model.installed) {
      elements.modelDetail.textContent = `${formatBytes(model.size_bytes)} · พร้อมใช้งาน · ${model.license}`;
      elements.modelAction.textContent = "ตรวจสอบไฟล์";
    } else if (status === "downloading") {
      elements.modelDetail.textContent = `กำลังดาวน์โหลด ${percent}% (${formatBytes(model.downloaded_bytes)} / ${formatBytes(model.size_bytes)})`;
      elements.modelAction.textContent = "ยกเลิก";
    } else {
      elements.modelDetail.textContent = model.error || `${formatBytes(model.size_bytes)} · ต้องดาวน์โหลดก่อนใช้งาน`;
      elements.modelAction.textContent = status === "failed" ? "ลองอีกครั้ง" : "ดาวน์โหลดโมเดล";
    }
    updateStartButton();
  }

  async function refreshModels(schedule = true) {
    try {
      const payload = await api("/api/models");
      state.models = payload.models;
      if (!selectedModel() && state.models.length) state.selectedModelId = state.models[0].id;
      renderModels();
      clearTimeout(state.modelTimer);
      if (schedule && state.models.some((model) => model.download_status === "downloading")) {
        state.modelTimer = setTimeout(() => refreshModels(true), 650);
      }
    } catch (error) {
      showToast(`ตรวจสอบโมเดลไม่สำเร็จ: ${error.message}`, true);
    }
  }

  function updateConversionControls() {
    const format = elements.outputFormat.value.toUpperCase();
    const cannotAlpha = format === "JPEG" || format === "BMP";
    elements.transparentBackground.disabled = cannotAlpha;
    elements.alphaWarning.hidden = !cannotAlpha;
    if (cannotAlpha) elements.colorBackground.checked = true;
    elements.backgroundColor.disabled = !elements.colorBackground.checked;
  }

  function updateStartButton() {
    const modelReady = state.operation !== "remove_background" || Boolean(selectedModel()?.installed);
    elements.startButton.disabled = state.busy || state.files.length === 0 || !modelReady;
    elements.startLabel.textContent = state.operation === "remove_background" ? "เริ่มลบพื้นหลัง" : "เริ่มแปลงไฟล์";
  }

  async function startJobs() {
    if (state.busy || !state.files.length) return;
    state.busy = true;
    updateStartButton();
    renderFiles();
    let uploadIds = [];
    try {
      const form = new FormData();
      state.files.forEach((item) => form.append("files", item.file, item.file.name));
      const uploaded = await api("/api/uploads", { method: "POST", body: form });
      uploadIds = uploaded.uploads.map((item) => item.id);
      const settings = state.operation === "remove_background"
        ? { model_id: state.selectedModelId }
        : {
            format: elements.outputFormat.value,
            quality: Number(elements.quality.value),
            background: elements.colorBackground.checked ? elements.backgroundColor.value : "transparent",
          };
      await api("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_ids: uploadIds, operation: state.operation, settings }),
      });
      revokeFiles();
      state.files = [];
      state.activeFile = 0;
      showToast("เพิ่มงานลงคิวแล้ว");
      await refreshJobs();
    } catch (error) {
      if (uploadIds.length) {
        api("/api/uploads/discard", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ upload_ids: uploadIds }),
        }).catch(() => {});
      }
      showToast(error.message, true);
    } finally {
      state.busy = false;
      renderFiles();
    }
  }

  function statusLabel(status) {
    return ({ queued: "รอคิว", running: "กำลังดำเนินการ", completed: "เสร็จสิ้น", failed: "ล้มเหลว", cancelled: "ยกเลิกแล้ว" })[status] || status;
  }

  function operationLabel(job) {
    if (job.operation === "remove_background") return `ลบพื้นหลัง (${job.settings.model_name})`;
    return `แปลงไฟล์ (${job.settings.format})`;
  }

  function renderJobs(jobs) {
    elements.queueCount.textContent = `(${jobs.length})`;
    const active = jobs.some((job) => !terminalStates.has(job.status));
    elements.cancelAll.disabled = !active;
    elements.queueBody.replaceChildren();
    if (!jobs.length) {
      const row = document.createElement("tr");
      row.className = "queue-empty";
      const cell = document.createElement("td");
      cell.colSpan = 5;
      cell.textContent = "ยังไม่มีงานในคิว";
      row.append(cell);
      elements.queueBody.append(row);
      return;
    }
    jobs.forEach((job) => {
      const row = document.createElement("tr");
      const fileCell = document.createElement("td");
      const fileBox = document.createElement("div");
      fileBox.className = "queue-file";
      const fileName = document.createElement("strong");
      fileName.textContent = job.filename;
      fileName.title = job.filename;
      const outputName = document.createElement("span");
      outputName.textContent = job.output_name || (job.error ? job.error : "ลบ metadata โดยอัตโนมัติ");
      fileBox.append(fileName, outputName);
      fileCell.append(fileBox);

      const operationCell = document.createElement("td");
      operationCell.textContent = operationLabel(job);
      const progressCell = document.createElement("td");
      const progressBox = document.createElement("div");
      progressBox.className = "job-progress";
      const track = document.createElement("div");
      track.className = "progress";
      const fill = document.createElement("span");
      fill.style.width = `${job.progress}%`;
      track.append(fill);
      const percent = document.createElement("span");
      percent.textContent = `${job.progress}%`;
      progressBox.append(track, percent);
      progressCell.append(progressBox);

      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = `status ${job.status}`;
      status.textContent = statusLabel(job.status);
      statusCell.append(status);

      const actionCell = document.createElement("td");
      if (job.output_ready) {
        const output = document.createElement("a");
        output.className = "queue-action";
        output.href = job.output_url;
        output.download = job.output_name || "image-output";
        output.textContent = "ดาวน์โหลด";
        actionCell.append(output);
      } else if (!terminalStates.has(job.status)) {
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "queue-action";
        cancel.textContent = "ยกเลิก";
        cancel.addEventListener("click", async () => {
          try { await api(`/api/jobs/${job.id}/cancel`, { method: "POST" }); await refreshJobs(); }
          catch (error) { showToast(error.message, true); }
        });
        actionCell.append(cancel);
      }
      row.append(fileCell, operationCell, progressCell, statusCell, actionCell);
      elements.queueBody.append(row);
    });
  }

  async function refreshJobs(schedule = true) {
    try {
      const payload = await api("/api/jobs");
      renderJobs(payload.jobs);
      clearTimeout(state.jobTimer);
      if (schedule && payload.jobs.some((job) => !terminalStates.has(job.status))) {
        state.jobTimer = setTimeout(() => refreshJobs(true), 650);
      }
    } catch (error) {
      showToast(`อ่านคิวงานไม่สำเร็จ: ${error.message}`, true);
    }
  }

  elements.chooseButton.addEventListener("click", () => elements.fileInput.click());
  elements.fileInput.addEventListener("change", () => { setFiles(elements.fileInput.files); elements.fileInput.value = ""; });
  ["dragenter", "dragover"].forEach((name) => elements.dropZone.addEventListener(name, (event) => { event.preventDefault(); elements.dropZone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((name) => elements.dropZone.addEventListener(name, (event) => { event.preventDefault(); elements.dropZone.classList.remove("dragover"); }));
  elements.dropZone.addEventListener("drop", (event) => setFiles(event.dataTransfer.files));
  elements.clearFiles.addEventListener("click", () => { revokeFiles(); state.files = []; state.activeFile = 0; renderFiles(); });

  elements.tabs.forEach((tab) => tab.addEventListener("click", () => {
    state.operation = tab.dataset.operation;
    elements.tabs.forEach((item) => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
    });
    elements.removePanel.hidden = state.operation !== "remove_background";
    elements.convertPanel.hidden = state.operation !== "convert";
    updateStartButton();
  }));

  elements.modelAction.addEventListener("click", async () => {
    const model = selectedModel();
    if (!model) return;
    try {
      if (model.installed) {
        const result = await api(`/api/models/${model.id}/verify`, { method: "POST" });
        showToast(result.valid ? "ไฟล์โมเดลถูกต้อง" : "ไฟล์โมเดลไม่ถูกต้องและถูกลบแล้ว", !result.valid);
      } else if (model.download_status === "downloading") {
        await api(`/api/models/${model.id}/cancel`, { method: "POST" });
      } else {
        await api(`/api/models/${model.id}/download`, { method: "POST" });
      }
      await refreshModels(true);
    } catch (error) { showToast(error.message, true); }
  });

  elements.outputFormat.addEventListener("change", updateConversionControls);
  elements.quality.addEventListener("input", () => { elements.qualityValue.textContent = elements.quality.value; });
  [elements.transparentBackground, elements.colorBackground].forEach((radio) => radio.addEventListener("change", updateConversionControls));
  elements.startButton.addEventListener("click", startJobs);
  elements.cancelAll.addEventListener("click", async () => {
    try { await api("/api/jobs/cancel-all", { method: "POST" }); await refreshJobs(); }
    catch (error) { showToast(error.message, true); }
  });
  window.addEventListener("beforeunload", revokeFiles);

  updateConversionControls();
  renderFiles();
  refreshModels(true);
  refreshJobs(true);
})();

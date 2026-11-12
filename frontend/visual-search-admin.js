"use strict";

(() => {
  const API = "http://localhost:8000";
  const authForm = document.querySelector("#visualAdminAuthForm");
  const tokenInput = document.querySelector("#visualAdminToken");
  const dashboard = document.querySelector("#visualAdminDashboard");
  const notice = document.querySelector("#visualAdminNotice");
  let adminToken = "";
  let pollTimer = 0;

  async function adminRequest(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      credentials: "omit",
      headers: {
        ...(options.headers || {}),
        "X-Admin-Token": adminToken
      }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }

  function setNotice(message, isError = false) {
    notice.textContent = message;
    notice.classList.toggle("is-error", isError);
  }

  function formatCount(value) {
    return Number(value || 0).toLocaleString("vi-VN");
  }

  function renderErrors(errors) {
    const body = document.querySelector("#visualAdminErrors");
    body.replaceChildren();
    if (!Array.isArray(errors) || !errors.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 4;
      cell.textContent = "Không có ảnh lỗi được ghi nhận.";
      return;
    }
    errors.slice(0, 100).forEach(error => {
      const row = body.insertRow();
      [error.MaSP, error.path, error.error, error.updated_at].forEach(value => {
        row.insertCell().textContent = String(value ?? "—");
      });
    });
  }

  function renderStatus(data) {
    const inventory = data.inventory || {};
    const index = data.index || {};
    const metrics = data.metrics || {};
    const withImages = Number(inventory.products_with_images || 0);
    const indexedProducts = Number(index.products_with_indexed_images || 0);
    const searches = Number(metrics.searches || 0);
    document.querySelector("#visualMetricProducts").textContent = formatCount(inventory.total_products);
    document.querySelector("#visualMetricWithImages").textContent = formatCount(withImages);
    document.querySelector("#visualMetricIndexed").textContent = `${formatCount(index.images_indexed)} ảnh / ${formatCount(indexedProducts)} SP`;
    document.querySelector("#visualMetricPending").textContent = formatCount(Math.max(0, withImages - indexedProducts));
    document.querySelector("#visualMetricErrors").textContent = formatCount(index.failed_images);
    document.querySelector("#visualMetricSuccess").textContent = withImages
      ? `${((indexedProducts / withImages) * 100).toFixed(1)}%`
      : "—";
    document.querySelector("#visualMetricLatency").textContent = metrics.average_search_ms == null
      ? "Chưa có dữ liệu"
      : `${formatCount(metrics.average_search_ms)} ms`;
    document.querySelector("#visualMetricSearches").textContent = searches
      ? `${formatCount(searches)} / ${((Number(metrics.match_rate || 0)) * 100).toFixed(1)}%`
      : "Chưa có dữ liệu";
    document.querySelector("#visualAdminModel").textContent =
      `${index.model || "OpenCLIP"} · ${index.pretrained || ""}`;
    document.querySelector("#visualAdminVision").textContent = data.gemini_vision_enabled
      ? "Gemini Vision: bật (ảnh gửi tới Google khi phân tích)"
      : "Gemini Vision: tắt (ảnh chỉ xử lý cục bộ)";
    const job = data.job || {};
    document.querySelector("#visualAdminJobStatus").textContent =
      `Chỉ mục ${index.ready ? "đã nạp" : "chưa nạp"} · Tác vụ: ${job.status || "idle"}`;
    renderErrors(index.errors);
    dashboard.hidden = false;
    document.querySelector("#visualAdminDisconnect").hidden = false;
  }

  async function refreshStatus() {
    const data = await adminRequest("/api/admin/visual-search/status");
    renderStatus(data);
    const job = data.job || {};
    if (job.status === "queued" || job.status === "running") {
      if (!pollTimer) pollTimer = window.setInterval(() => refreshStatus().catch(handleError), 2000);
    } else if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = 0;
    }
    return data;
  }

  function handleError(error) {
    setNotice(error.message, true);
    if (/token|quyền|cấu hình/i.test(error.message)) {
      dashboard.hidden = true;
      document.querySelector("#visualAdminDisconnect").hidden = true;
    }
  }

  authForm.addEventListener("submit", async event => {
    event.preventDefault();
    adminToken = tokenInput.value.trim();
    if (!adminToken) return;
    try {
      await refreshStatus();
      setNotice("Đã kết nối dashboard quản trị.");
    } catch (error) {
      adminToken = "";
      handleError(error);
    }
  });

  document.querySelector("#visualAdminDisconnect").addEventListener("click", () => {
    adminToken = "";
    tokenInput.value = "";
    dashboard.hidden = true;
    document.querySelector("#visualAdminDisconnect").hidden = true;
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = 0;
    setNotice("Đã ngắt kết nối.");
  });

  document.querySelector("#visualAdminRefresh").addEventListener("click", () => {
    refreshStatus().then(() => setNotice("Đã cập nhật trạng thái.")).catch(handleError);
  });

  async function startJob(path) {
    const result = await adminRequest(path, { method: "POST" });
    setNotice(`Đã xếp hàng tác vụ ${result.id}.`);
    await refreshStatus();
  }

  document.querySelector("#visualAdminSync").addEventListener("click", () => {
    startJob("/api/admin/visual-search/sync").catch(handleError);
  });
  document.querySelector("#visualAdminRetry").addEventListener("click", () => {
    startJob("/api/admin/visual-search/retry-failed").catch(handleError);
  });
})();

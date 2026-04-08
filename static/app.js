(function () {
    const body = document.body;
    const page = body.dataset.page || "";
    const currentDeviceName = body.dataset.deviceName || "";
    const selectedDevice = body.dataset.selectedDevice || "";
    const selectedStatus = body.dataset.selectedStatus || "";
    const liveLogElement = document.getElementById("live-log");
    const flashElement = document.getElementById("flash-message");
    const storageKey = "wimill-ui-live-log";

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function getLogs() {
        try {
            return JSON.parse(sessionStorage.getItem(storageKey) || "[]");
        } catch {
            return [];
        }
    }

    function saveLogs(items) {
        sessionStorage.setItem(storageKey, JSON.stringify(items.slice(-80)));
    }

    function renderLiveLog() {
        if (!liveLogElement) {
            return;
        }
        const logs = getLogs();
        if (!logs.length) {
            liveLogElement.innerHTML = '<div class="live-log-line info">UI log is empty.</div>';
            return;
        }
        liveLogElement.innerHTML = logs
            .map((item) => `<div class="live-log-line ${escapeHtml(item.level)}"><strong>${escapeHtml(item.time)}</strong> ${escapeHtml(item.message)}</div>`)
            .join("");
        liveLogElement.scrollTop = liveLogElement.scrollHeight;
    }

    function logLine(message, level = "info") {
        const time = new Date().toLocaleTimeString();
        const logs = getLogs();
        logs.push({ time, message, level });
        saveLogs(logs);
        renderLiveLog();
        console.log(`[WiMill UI][${level}] ${message}`);
    }

    function badgeClass(value) {
        const safe = String(value || "unknown").toLowerCase();
        if (["ok", "done", "online", "idle", "attached"].includes(safe)) return "badge-ok";
        if (["pending", "queued", "detached", "switching"].includes(safe)) return "badge-pending";
        if (["running"].includes(safe)) return "badge-running";
        if (["error", "offline", "busy"].includes(safe)) return "badge-danger";
        return "badge-neutral";
    }

    function formatBytes(value) {
        if (value === null || value === undefined || value === "") {
            return "-";
        }
        const size = Number(value);
        if (Number.isNaN(size)) {
            return String(value);
        }
        if (size < 1024) return `${size} B`;
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
        if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
        return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
    }

    function attachFormLogging() {
        document.querySelectorAll("form").forEach((form) => {
            form.addEventListener("submit", () => {
                const label = form.dataset.logLabel || form.action || "form submit";
                logLine(`Submitting: ${label}`, "info");
            });
        });
        const clearButton = document.getElementById("clear-live-log");
        if (clearButton) {
            clearButton.addEventListener("click", () => {
                sessionStorage.removeItem(storageKey);
                renderLiveLog();
            });
        }
    }

    async function fetchJson(url) {
        logLine(`GET ${url}`, "info");
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        const size = Array.isArray(data) ? data.length : Object.keys(data || {}).length;
        logLine(`Response ${url}: ${size}`, "success");
        return data;
    }

    function renderDashboard(devices, jobs, activity) {
        const deviceStats = {
            devices_total: devices.length,
            devices_online: devices.filter((item) => item.is_online).length,
            devices_offline: devices.filter((item) => !item.is_online).length,
        };
        const jobStats = {
            jobs_pending: jobs.filter((item) => item.status === "pending" || item.status === "queued").length,
            jobs_running: jobs.filter((item) => item.status === "running").length,
            jobs_done: jobs.filter((item) => item.status === "done").length,
            jobs_error: jobs.filter((item) => item.status === "error").length,
        };

        Object.entries({ ...deviceStats, ...jobStats }).forEach(([key, value]) => {
            const element = document.querySelector(`[data-stat='${key}']`);
            if (element) {
                element.textContent = value;
            }
        });

        const activityBody = document.getElementById("dashboard-activity-body");
        if (activityBody) {
            const rows = activity.slice(0, 10).map((entry) => `
                <tr>
                    <td>${escapeHtml(entry.timestamp)}</td>
                    <td>${escapeHtml(entry.device_name || "-")}</td>
                    <td>${escapeHtml(entry.event_type)}</td>
                    <td><span class="badge ${badgeClass(entry.status)}">${escapeHtml(entry.status)}</span></td>
                    <td>${escapeHtml(entry.details || entry.response_summary || "-")}</td>
                </tr>
            `).join("");
            activityBody.innerHTML = rows || '<tr><td colspan="5" class="empty-state">No activity yet.</td></tr>';
        }
    }

    function renderDevices(devices) {
        const bodyEl = document.getElementById("devices-table-body");
        if (!bodyEl) return;
        bodyEl.innerHTML = devices.map((device) => `
            <tr>
                <td>${escapeHtml(device.device_name)}</td>
                <td><span class="badge ${badgeClass(device.is_online ? "online" : "offline")}">${device.is_online ? "online" : "offline"}</span></td>
                <td><span class="badge ${badgeClass(device.usb_status)}">${escapeHtml(device.usb_status)}</span></td>
                <td><span class="badge ${badgeClass(device.busy_status)}">${escapeHtml(device.busy_status)}</span></td>
                <td>${formatBytes(device.free_space)}</td>
                <td>${escapeHtml(device.firmware_version || "-")}</td>
                <td>${escapeHtml(device.last_seen || "-")}</td>
                <td>
                    <div class="button-row">
                        <form method="post" action="/ui/device/${encodeURIComponent(device.device_name)}/attach" data-log-label="Attach ${escapeHtml(device.device_name)}">
                            <button type="submit" class="button button-ok">Attach</button>
                        </form>
                        <form method="post" action="/ui/device/${encodeURIComponent(device.device_name)}/detach" data-log-label="Detach ${escapeHtml(device.device_name)}">
                            <button type="submit" class="button button-pending">Detach</button>
                        </form>
                        <a href="/ui/files/device/${encodeURIComponent(device.device_name)}" class="button button-muted">Files</a>
                        <form method="post" action="/ui/device/${encodeURIComponent(device.device_name)}/refresh" data-log-label="Refresh files ${escapeHtml(device.device_name)}">
                            <button type="submit" class="button button-muted">Refresh Files</button>
                        </form>
                    </div>
                </td>
            </tr>
        `).join("") || '<tr><td colspan="8" class="empty-state">No allowed devices yet.</td></tr>';
        attachFormLogging();
    }

    function renderJobs(jobs) {
        const bodyEl = document.getElementById("jobs-table-body");
        if (!bodyEl) return;
        bodyEl.innerHTML = jobs.map((job) => {
            const actions = ["done", "error"].includes(job.status)
                ? '<span class="helper-text">-</span>'
                : `
                    <form method="post" action="/ui/jobs/${encodeURIComponent(job.id)}/finish" data-log-label="Finish job ${escapeHtml(job.id)}">
                        <button type="submit" class="button button-pending">Finish</button>
                    </form>
                `;
            return `
                <tr>
                    <td>${escapeHtml(job.id)}</td>
                    <td>${escapeHtml(job.device_name || "-")}</td>
                    <td>${escapeHtml(job.job_type)}</td>
                    <td>${escapeHtml(job.file_name || "-")}</td>
                    <td><span class="badge ${badgeClass(job.status)}">${escapeHtml(job.status)}</span></td>
                    <td>${escapeHtml(job.progress)}%</td>
                    <td>${escapeHtml(job.created_at)}</td>
                    <td>${escapeHtml(job.updated_at || "-")}</td>
                    <td>${escapeHtml(job.error_message || "-")}</td>
                    <td>${actions}</td>
                </tr>
            `;
        }).join("") || '<tr><td colspan="10" class="empty-state">No jobs match the current filter.</td></tr>';
        attachFormLogging();
    }

    function renderActivity(activity) {
        const bodyEl = document.getElementById("activity-table-body");
        if (!bodyEl) return;
        bodyEl.innerHTML = activity.map((entry) => `
            <tr>
                <td>${escapeHtml(entry.timestamp)}</td>
                <td>${escapeHtml(entry.device_name || "-")}</td>
                <td>${escapeHtml(entry.endpoint)}</td>
                <td>${escapeHtml(entry.event_type)}</td>
                <td><span class="badge ${badgeClass(entry.status)}">${escapeHtml(entry.status)}</span></td>
                <td>${escapeHtml(entry.details || entry.response_summary || entry.request_summary || "-")}</td>
            </tr>
        `).join("") || '<tr><td colspan="6" class="empty-state">No activity yet.</td></tr>';
    }

    function renderDeviceFiles(deviceFiles) {
        const bodyEl = document.getElementById("device-files-table-body");
        if (!bodyEl) return;
        bodyEl.innerHTML = deviceFiles.map((item) => {
            const action = item.is_dir
                ? '<span class="helper-text">-</span>'
                : `
                    <form method="post" action="/ui/device/${encodeURIComponent(currentDeviceName)}/download" data-log-label="Download ${escapeHtml(item.file_name)} from ${escapeHtml(currentDeviceName)}">
                        <input type="hidden" name="file_name" value="${escapeHtml(item.file_name)}">
                        <button type="submit" class="button button-pending">Download to Server</button>
                    </form>
                `;
            return `
                <tr>
                    <td><span class="badge ${item.is_dir ? "badge-pending" : "badge-neutral"}">${item.is_dir ? "DIR" : "FILE"}</span></td>
                    <td>${escapeHtml(item.file_name)}</td>
                    <td>${item.is_dir ? "-" : formatBytes(item.file_size)}</td>
                    <td>${escapeHtml(item.modified_at || "-")}</td>
                    <td>${escapeHtml(item.synced_at)}</td>
                    <td>${action}</td>
                </tr>
            `;
        }).join("") || '<tr><td colspan="6" class="empty-state">No files reported by this device yet.</td></tr>';
        attachFormLogging();
    }

    async function refreshUi() {
        try {
            const jobsUrl = (() => {
                const params = new URLSearchParams();
                if (selectedDevice) params.set("device_name", selectedDevice);
                if (selectedStatus) params.set("status", selectedStatus);
                params.set("limit", page === "jobs" ? "200" : "100");
                return `/jobs?${params.toString()}`;
            })();

            const requests = [
                fetchJson("/devices"),
                fetchJson(jobsUrl),
                fetchJson(page === "dashboard" ? "/activity?limit=10" : "/activity?limit=100"),
            ];
            if (page === "files_device" && currentDeviceName) {
                requests.push(fetchJson(`/files/device/${encodeURIComponent(currentDeviceName)}`));
            }

            const [devices, jobs, activity, deviceFiles] = await Promise.all(requests);

            renderDashboard(devices, jobs, activity);
            renderDevices(devices);
            renderJobs(jobs);
            renderActivity(activity);
            if (deviceFiles) {
                renderDeviceFiles(deviceFiles);
            }
        } catch (error) {
            logLine(`Refresh failed: ${error.message}`, "error");
        }
    }

    renderLiveLog();
    attachFormLogging();

    if (flashElement && flashElement.textContent.trim()) {
        logLine(flashElement.textContent.trim(), "success");
    }

    refreshUi();
    window.setInterval(refreshUi, 5000);
})();

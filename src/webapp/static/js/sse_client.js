/**
 * SSE client — connects to /api/events and dispatches events to HTMX.
 * Handles reconnection on disconnect.
 */

(function () {
  let evtSource = null;
  let retryDelay = 1000;
  const MAX_RETRY = 30_000;

  function connect() {
    evtSource = new EventSource("/api/events");

    evtSource.onopen = function () {
      retryDelay = 1000;
      console.log("[SSE] connected");
    };

    evtSource.onmessage = function (event) {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return; // keepalive comment or malformed — ignore
      }
      handleEvent(data);
    };

    evtSource.onerror = function () {
      console.warn("[SSE] disconnected, retrying in", retryDelay, "ms");
      evtSource.close();
      setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, MAX_RETRY);
    };
  }

  function handleEvent(data) {
    const type = data.type;

    if (type === "gate_progress") {
      appendLog(`Gate ${data.gate} ${data.status}: exp#${data.exp_id} — ${data.reason || ""}`);
      // Trigger HTMX refresh on pipeline board
      htmx.trigger(document.body, "pipelineUpdate");
    }

    if (type === "gate_error") {
      appendLog(`ERROR in ${data.gate} exp#${data.exp_id}: ${data.error}`, true);
    }

    if (type === "fwd_ready") {
      appendLog(`FWD_READY: ${data.strategy} ${data.ticker} OOS PF=${data.oos_pf}`);
      // Show browser notification if available
      if (Notification && Notification.permission === "granted") {
        new Notification("FWD_READY", {
          body: `${data.strategy} ${data.ticker} is ready for review!`
        });
      }
    }
  }

  function appendLog(msg, isError = false) {
    const container = document.getElementById("log-tail");
    if (!container) return;
    const line = document.createElement("div");
    const now = new Date().toTimeString().slice(0, 8);
    line.className = isError ? "text-red-400" : "text-gray-300";
    line.textContent = `[${now}] ${msg}`;
    container.prepend(line);
    // Keep only last 50 lines
    while (container.children.length > 50) {
      container.removeChild(container.lastChild);
    }
  }

  // Request notification permission
  if (Notification && Notification.permission === "default") {
    Notification.requestPermission();
  }

  connect();
})();

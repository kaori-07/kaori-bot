// dashboard/static/app.js
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---------------------------------------------------------------
  // Reveal-on-load animation (fade + slide up, staggered via --delay)
  // ---------------------------------------------------------------
  function initReveal() {
    const els = $$(".reveal");
    els.forEach((el) => {
      requestAnimationFrame(() => {
        setTimeout(() => el.classList.add("in"), 20);
      });
    });
  }

  // ---------------------------------------------------------------
  // Flash messages -> animated toasts
  // ---------------------------------------------------------------
  function initToasts() {
    const stack = $("#toast-stack");
    const source = $("[data-flash-source]");
    if (!stack || !source) return;

    $$("[data-flash]", source).forEach((el, i) => {
      const isError = el.classList.contains("flash-error");
      spawnToast(el.textContent.trim(), isError ? "error" : "success", i * 120);
    });
    source.remove();
  }

  function spawnToast(message, kind = "success", delay = 0) {
    const stack = $("#toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast toast-${kind}`;
    el.textContent = message;
    setTimeout(() => {
      stack.appendChild(el);
      requestAnimationFrame(() => el.classList.add("in"));
      setTimeout(() => {
        el.classList.remove("in");
        el.classList.add("out");
        setTimeout(() => el.remove(), 300);
      }, 4200);
    }, delay);
  }

  // ---------------------------------------------------------------
  // Count-up number animation
  // ---------------------------------------------------------------
  function animateNumber(el, to) {
    const from = parseInt(el.dataset.value || el.textContent, 10) || 0;
    to = Number(to) || 0;
    if (from === to) {
      el.dataset.value = to;
      return;
    }
    const duration = 500;
    const start = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const val = Math.round(from + (to - from) * eased);
      el.textContent = val;
      if (p < 1) requestAnimationFrame(tick);
      else el.dataset.value = to;
    }
    requestAnimationFrame(tick);
  }

  // ---------------------------------------------------------------
  // Live status polling (every page with the sidebar)
  // ---------------------------------------------------------------
  function formatDuration(totalSeconds) {
    if (totalSeconds == null) return "—";
    const d = Math.floor(totalSeconds / 86400);
    const h = Math.floor((totalSeconds % 86400) / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = Math.floor(totalSeconds % 60);
    if (d > 0) return `${d}d ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function initLivePolling() {
    const navDot = $("#nav-dot");
    const navLatency = $("#nav-latency");
    if (!navDot && !navLatency) return;

    const guildCountEl = $('[data-live="guild_count"]');
    const userCountEl = $('[data-live="user_count"]');
    const latencyEl = $('[data-live="latency_ms"]');
    const statusEl = $('[data-live="status_text"]');
    const statusDot = $('[data-live="status_dot"]');
    const cpuEl = $('[data-live="cpu_percent"]');
    const memEl = $('[data-live="memory_mb"]');
    const cmdEl = $('[data-live="command_count"]');
    const cogCountEl = $('[data-live="cog_loaded_count"]');
    const shardEl = $('[data-live="shard_count"]');
    const uptimeEl = $('[data-live="uptime"]');

    let uptimeBaseSeconds = null;
    let uptimeBaseAt = null;

    // ticks the uptime display every second between poll cycles, so it
    // counts up smoothly instead of jumping every 4s
    setInterval(() => {
      if (uptimeEl && uptimeBaseSeconds != null) {
        const elapsed = (Date.now() - uptimeBaseAt) / 1000;
        uptimeEl.textContent = formatDuration(uptimeBaseSeconds + elapsed);
      }
    }, 1000);

    async function poll() {
      try {
        const res = await fetch("/api/live", { headers: { "X-Requested-With": "fetch" } });
        if (!res.ok) return;
        const data = await res.json();

        if (navDot) navDot.className = `dot pulse-dot ${data.online ? "dot-on" : "dot-off"}`;
        if (statusDot) statusDot.className = `dot pulse-dot ${data.online ? "dot-on" : "dot-off"}`;
        if (statusEl) statusEl.textContent = data.online ? "Online" : "Offline";
        if (navLatency) navLatency.textContent = data.latency_ms != null ? `${data.latency_ms}ms` : "— ms";

        if (guildCountEl) animateNumber(guildCountEl, data.guild_count);
        if (userCountEl) animateNumber(userCountEl, data.user_count);
        if (latencyEl) latencyEl.textContent = data.latency_ms != null ? `${data.latency_ms}ms` : "—";

        const sys = data.system || {};
        if (cpuEl) cpuEl.textContent = sys.cpu_percent != null ? `${sys.cpu_percent.toFixed(1)}%` : "—";
        if (memEl) memEl.textContent = sys.memory_mb != null ? `${sys.memory_mb} MB` : "—";
        if (cmdEl) cmdEl.textContent = data.command_count != null ? data.command_count : "—";
        if (cogCountEl) cogCountEl.textContent = data.cog_loaded_count != null ? data.cog_loaded_count : "—";
        if (shardEl) shardEl.textContent = data.shard_count != null ? data.shard_count : "1 (unsharded)";
        if (uptimeEl && data.uptime_seconds != null) {
          uptimeBaseSeconds = data.uptime_seconds;
          uptimeBaseAt = Date.now();
          uptimeEl.textContent = formatDuration(uptimeBaseSeconds);
        }

        // sync cog "loaded" pills if present
        (data.cogs || []).forEach((c) => {
          const row = document.querySelector(`[data-cog-row="${c.name}"]`);
          if (!row) return;
          const pill = row.querySelector(".pill");
          if (pill) {
            pill.textContent = c.loaded ? "loaded" : "not loaded";
            pill.className = `pill ${c.loaded ? "pill-on" : "pill-off"}`;
          }
        });
      } catch (e) {
        if (navDot) navDot.className = "dot pulse-dot dot-off";
      }
    }

    poll();
    setInterval(poll, 4000);
  }

  // ---------------------------------------------------------------
  // Live logs console
  // ---------------------------------------------------------------
  function initLogConsole() {
    const consoleEl = $("#console");
    if (!consoleEl) return;
    const clearBtn = $("#clear-logs");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        consoleEl.innerHTML = "";
      });
    }

    async function poll() {
      const lastId = parseInt(consoleEl.dataset.lastId || "0", 10);
      try {
        const res = await fetch(`/api/logs?since=${lastId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.logs || !data.logs.length) return;

        const atBottom = consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 60;

        data.logs.forEach((entry) => {
          const line = document.createElement("div");
          line.className = `console-line level-${entry.level.toLowerCase()} line-enter`;
          const lvl = document.createElement("span");
          lvl.className = "console-lvl";
          lvl.textContent = entry.level;
          const msg = document.createElement("span");
          msg.className = "console-msg";
          msg.textContent = entry.message;
          line.appendChild(lvl);
          line.appendChild(msg);
          consoleEl.appendChild(line);
          requestAnimationFrame(() => line.classList.add("in"));
          consoleEl.dataset.lastId = entry.id;
        });

        // keep DOM light
        while (consoleEl.children.length > 400) {
          consoleEl.removeChild(consoleEl.firstChild);
        }

        if (atBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
      } catch (e) {
        /* silent - will retry next tick */
      }
    }

    consoleEl.scrollTop = consoleEl.scrollHeight;
    poll();
    setInterval(poll, 2000);
  }

  // ---------------------------------------------------------------
  // Toggle switches: optimistic UI flip before the page reload lands
  // ---------------------------------------------------------------
  function initSwitches() {
    $$(".switch").forEach((btn) => {
      btn.addEventListener("click", () => {
        btn.classList.toggle("switch-on");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initReveal();
    initToasts();
    initLivePolling();
    initLogConsole();
    initSwitches();
  });
})();

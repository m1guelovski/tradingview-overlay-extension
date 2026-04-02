// Exposed as a global for MV3 content scripts (no ES modules).
window.OverlayView = class OverlayView {
  constructor({ parent }) {
    this.parent = parent || document.body;
    this.container = null;
    this.contentEl = null;
    this.headerEl = null;
    this.groupsEl = null;
    this.totalPnLEl = null;
    this.totalPositionsEl = null;
    this.updatedAtEl = null;
    this.minimizeBtn = null;
    this.closeBtn = null;
    this.reopenBtn = null;

    this.minimized = false;
    this.closed = false;

    this.expandedCurrencies = new Set();
    this.expandedPairs = new Set(); // `${currency}::${symbol}`
    this.lastModel = null;
  }

  init() {
    this.container = document.createElement("section");
    this.container.id = "tv-overlay-panel";
    this.container.setAttribute("role", "status");
    this.container.setAttribute("aria-live", "polite");
    this.container.innerHTML = `
      <div class="tv-overlay-panel__header" data-ui="header">
        <div class="tv-overlay-panel__title">Quote Exposure</div>
        <div class="tv-overlay-panel__header-actions">
          <button type="button" class="tv-overlay-panel__icon-btn" data-ui="minimize" aria-label="Minimize panel">—</button>
          <button type="button" class="tv-overlay-panel__icon-btn" data-ui="close" aria-label="Close panel">×</button>
        </div>
      </div>

      <div class="tv-overlay-panel__content" data-ui="content">
        <div class="tv-overlay-panel__totals">
          <div class="tv-overlay-panel__totals-row">
            <span class="tv-overlay-panel__muted">Total PnL</span>
            <span class="tv-overlay-panel__total-pnl tv-overlay-panel__num--neu" data-ui="totalPnl">No data</span>
          </div>
          <div class="tv-overlay-panel__totals-row">
            <span class="tv-overlay-panel__muted" data-ui="totalCount">0 positions</span>
          </div>
          <div class="tv-overlay-panel__totals-row">
            <span class="tv-overlay-panel__muted">Updated</span>
            <span class="tv-overlay-panel__muted" data-metric="updatedAt">—</span>
          </div>
        </div>

        <div class="tv-overlay-panel__table-head">
          <div class="tv-overlay-panel__col-label">Label</div>
          <div class="tv-overlay-panel__col-pnl">PnL</div>
          <div class="tv-overlay-panel__col-count">#</div>
        </div>

        <div class="tv-overlay-panel__rows" data-ui="groups">
          <div class="tv-overlay-panel__empty">No data</div>
        </div>
      </div>
    `;

    this.parent.appendChild(this.container);
    this.cacheRefs();
    this.createReopenButton();
    this.bindEventsOnce();
    this.loadSettingsAndApply();
  }

  attach() {
    this.container = document.getElementById("tv-overlay-panel");
    if (!this.container) return false;

    this.cacheRefs();
    if (!document.getElementById("tv-overlay-reopen")) {
      this.createReopenButton();
    } else {
      this.reopenBtn = document.getElementById("tv-overlay-reopen");
    }

    this.bindEventsOnce();
    this.loadSettingsAndApply();
    return Boolean(this.container && this.headerEl && this.groupsEl);
  }

  cacheRefs() {
    this.headerEl = this.container.querySelector('[data-ui="header"]');
    this.contentEl = this.container.querySelector('[data-ui="content"]');
    this.groupsEl = this.container.querySelector('[data-ui="groups"]');
    this.totalPnLEl = this.container.querySelector('[data-ui="totalPnl"]');
    this.totalPositionsEl = this.container.querySelector('[data-ui="totalCount"]');
    this.updatedAtEl = this.container.querySelector('[data-metric="updatedAt"]');
    this.minimizeBtn = this.container.querySelector('[data-ui="minimize"]');
    this.closeBtn = this.container.querySelector('[data-ui="close"]');
  }

  setModel(model, updatedAt) {
    this.lastModel = model;
    const groups = Array.isArray(model?.currencyGroups) ? model.currencyGroups : [];

    const totalPnL = groups.reduce((sum, g) => sum + (Number(g.totalProfit) || 0), 0);
    const totalCount = groups.reduce((sum, g) => sum + (Number(g.count) || 0), 0);

    if (this.totalPnLEl) {
      if (!groups.length) {
        this.totalPnLEl.textContent = "No data";
      } else {
        this.totalPnLEl.textContent = `${totalPnL >= 0 ? "+" : ""}${totalPnL.toFixed(2)}`;
      }
      this.totalPnLEl.className = `tv-overlay-panel__total-pnl ${this.pnlClass(totalPnL)}`;
    }
    if (this.totalPositionsEl) {
      this.totalPositionsEl.textContent = `${totalCount} position${totalCount === 1 ? "" : "s"}`;
    }
    if (this.updatedAtEl) {
      this.updatedAtEl.textContent =
        updatedAt instanceof Date && !Number.isNaN(updatedAt.getTime())
          ? updatedAt.toLocaleTimeString()
          : "—";
    }

    this.renderRows(groups);
  }

  renderRows(groups) {
    if (!this.groupsEl) return;
    if (!groups.length) {
      this.groupsEl.innerHTML = `<div class="tv-overlay-panel__empty">No data</div>`;
      return;
    }

    const worstCurrency = groups[0]?.currency || null;

    this.groupsEl.innerHTML = groups
      .map((g) => {
        const currencyExpanded = this.expandedCurrencies.has(g.currency);
        const currencyCaret = currencyExpanded ? "▾" : "▸";
        const currencyRowClass =
          "tv-overlay-panel__row-grid tv-overlay-panel__row-grid--currency" +
          (g.currency === worstCurrency ? " tv-overlay-panel__row-grid--worst" : "");

        const pairs = Array.isArray(g.pairs) ? g.pairs : [];
        const worstPair = pairs[0]?.symbol || null;

        return `
          <div class="tv-overlay-panel__block" data-currency="${g.currency}">
            <div class="${currencyRowClass}" data-ui="currency-toggle">
              <div class="tv-overlay-panel__col-label">
                <span class="tv-overlay-panel__caret">${currencyCaret}</span>
                <span class="tv-overlay-panel__label-main">${g.currency}</span>
              </div>
              <div class="tv-overlay-panel__col-pnl">
                <span class="tv-overlay-panel__pnl ${this.pnlClass(g.totalProfit)}">${this.formatPnl(g.totalProfit)}</span>
              </div>
              <div class="tv-overlay-panel__col-count">
                <span class="tv-overlay-panel__count">${g.count || 0}</span>
              </div>
            </div>
            ${currencyExpanded ? this.renderPairs(g.currency, pairs, worstPair) : ""}
          </div>
        `;
      })
      .join("");
  }

  renderPairs(currency, pairs, worstPairSymbol) {
    if (!pairs.length) return `<div class="tv-overlay-panel__empty tv-overlay-panel__empty--nested">No pairs</div>`;

    return pairs
      .map((p) => {
        const key = `${currency}::${p.symbol}`;
        const pairExpanded = this.expandedPairs.has(key);
        const pairCaret = pairExpanded ? "▾" : "▸";
        const positions = Array.isArray(p.positions) ? p.positions : [];
        const pairRowClass =
          "tv-overlay-panel__row-grid tv-overlay-panel__row-grid--pair" +
          (p.symbol === worstPairSymbol ? " tv-overlay-panel__row-grid--worst" : "");

        return `
          <div class="tv-overlay-panel__block" data-pair="${p.symbol}">
            <div class="${pairRowClass}" data-ui="pair-toggle">
              <div class="tv-overlay-panel__col-label tv-overlay-panel__indent-pair">
                <span class="tv-overlay-panel__caret">${pairCaret}</span>
                <span class="tv-overlay-panel__label-sub">${p.symbol}</span>
              </div>
              <div class="tv-overlay-panel__col-pnl">
                <span class="tv-overlay-panel__pnl ${this.pnlClass(p.totalProfit)}">${this.formatPnl(p.totalProfit)}</span>
              </div>
              <div class="tv-overlay-panel__col-count">
                <span class="tv-overlay-panel__count">${p.count || 0}</span>
              </div>
            </div>
            ${pairExpanded ? this.renderPositions(positions) : ""}
          </div>
        `;
      })
      .join("");
  }

  renderPositions(positions) {
    const sorted = positions
      .slice()
      .sort((a, b) => (a?.profit ?? 0) - (b?.profit ?? 0));

    return sorted
      .map((pos, idx) => `
        <div class="tv-overlay-panel__row-grid tv-overlay-panel__row-grid--position">
          <div class="tv-overlay-panel__col-label tv-overlay-panel__indent-pos">
            <span class="tv-overlay-panel__label-pos">#${idx + 1}</span>
          </div>
          <div class="tv-overlay-panel__col-pnl">
            <span class="tv-overlay-panel__pnl ${this.pnlClass(pos?.profit || 0)}">${this.formatPnl(pos?.profit || 0)}</span>
          </div>
          <div class="tv-overlay-panel__col-count">
            <span class="tv-overlay-panel__count"> </span>
          </div>
        </div>
      `)
      .join("");
  }

  pnlClass(value) {
    if (value < -200) return "tv-overlay-panel__num--neg-strong";
    if (value < -50) return "tv-overlay-panel__num--neg-soft";
    if (value > 50) return "tv-overlay-panel__num--pos";
    return "tv-overlay-panel__num--neu";
  }

  formatPnl(value) {
    const n = Number(value) || 0;
    return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
  }

  bindEventsOnce() {
    if (!this.container || this.container.dataset.eventsBound === "1") return;
    this.container.dataset.eventsBound = "1";

    // Drag
    let dragState = null;
    const onPointerDown = (e) => {
      if (this.closed) return;
      if (e.button !== undefined && e.button !== 0) return;
      if (e.target.closest("[data-ui='minimize']") || e.target.closest("[data-ui='close']")) return;

      const rect = this.container.getBoundingClientRect();
      dragState = { offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top };
      e.preventDefault();
    };
    const onPointerMove = (e) => {
      if (!dragState) return;
      const margin = 8;
      const w = this.container.offsetWidth;
      const h = this.container.offsetHeight;
      let left = e.clientX - dragState.offsetX;
      let top = e.clientY - dragState.offsetY;
      left = Math.max(margin, Math.min(left, window.innerWidth - w - margin));
      top = Math.max(margin, Math.min(top, window.innerHeight - h - margin));
      this.container.style.left = `${left}px`;
      this.container.style.top = `${top}px`;
      this.container.style.right = "auto";
      this.container.style.bottom = "auto";
    };
    const onPointerUp = () => {
      if (!dragState) return;
      dragState = null;
      this.saveSettings();
    };
    this.headerEl?.addEventListener("mousedown", onPointerDown);
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);

    // Controls
    this.minimizeBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.setMinimized(!this.minimized);
    });
    this.closeBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.setClosed(true);
    });
    this.reopenBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.setClosed(false);
    });

    // Expand / collapse rows
    this.groupsEl?.addEventListener("click", (e) => {
      const currencyRow = e.target.closest("[data-ui='currency-toggle']");
      if (currencyRow) {
        const block = currencyRow.closest("[data-currency]");
        const currency = block?.getAttribute("data-currency");
        if (!currency) return;
        if (this.expandedCurrencies.has(currency)) this.expandedCurrencies.delete(currency);
        else this.expandedCurrencies.add(currency);
        this.renderRows(Array.isArray(this.lastModel?.currencyGroups) ? this.lastModel.currencyGroups : []);
        return;
      }

      const pairRow = e.target.closest("[data-ui='pair-toggle']");
      if (pairRow) {
        const currencyBlock = pairRow.closest("[data-currency]");
        const pairBlock = pairRow.closest("[data-pair]");
        const currency = currencyBlock?.getAttribute("data-currency");
        const pair = pairBlock?.getAttribute("data-pair");
        if (!currency || !pair) return;
        const key = `${currency}::${pair}`;
        if (this.expandedPairs.has(key)) this.expandedPairs.delete(key);
        else this.expandedPairs.add(key);
        this.renderRows(Array.isArray(this.lastModel?.currencyGroups) ? this.lastModel.currencyGroups : []);
      }
    });
  }

  setMinimized(next) {
    this.minimized = Boolean(next);
    if (this.contentEl) this.contentEl.style.display = this.minimized ? "none" : "";
    if (this.minimizeBtn) this.minimizeBtn.textContent = this.minimized ? "+" : "—";
    this.saveSettings();
  }

  setClosed(next) {
    this.closed = Boolean(next);
    if (!this.container || !this.reopenBtn) return;
    if (this.closed) {
      this.container.style.display = "none";
      this.reopenBtn.style.display = "";
    } else {
      this.container.style.display = "";
      this.reopenBtn.style.display = "none";
    }
  }

  createReopenButton() {
    if (document.getElementById("tv-overlay-reopen")) {
      this.reopenBtn = document.getElementById("tv-overlay-reopen");
      return;
    }
    const btn = document.createElement("button");
    btn.id = "tv-overlay-reopen";
    btn.className = "tv-overlay-reopen-btn";
    btn.type = "button";
    btn.textContent = "TV";
    btn.setAttribute("aria-label", "Reopen Quote Exposure panel");
    btn.style.display = "none";
    this.parent.appendChild(btn);
    this.reopenBtn = btn;
  }

  loadSettingsAndApply() {
    try {
      chrome.storage?.local?.get(["panelPosition", "minimized"], (res) => {
        const panelPosition = res?.panelPosition || null;
        const minimized = Boolean(res?.minimized);
        if (panelPosition && typeof panelPosition.left === "number" && typeof panelPosition.top === "number") {
          this.container.style.left = `${panelPosition.left}px`;
          this.container.style.top = `${panelPosition.top}px`;
          this.container.style.right = "auto";
          this.container.style.bottom = "auto";
        }
        this.setMinimized(minimized);
      });
    } catch (e) {
      // no-op
    }
  }

  saveSettings() {
    try {
      const left = parseFloat(this.container?.style?.left || "");
      const top = parseFloat(this.container?.style?.top || "");
      const payload = { minimized: this.minimized };
      if (Number.isFinite(left) && Number.isFinite(top)) {
        payload.panelPosition = { left, top };
      }
      chrome.storage?.local?.set(payload, () => {});
    } catch (e) {
      // no-op
    }
  }
};


(async () => {
  const { extractQuoteCurrency } = await import(chrome.runtime.getURL("src/utils/exposureUtils.js"));

  let overlayInstance = null;

  const DEBUG_PREFIX = "[Currency Exposure]";

const REGEX = {
  symbolLettersOnly: /[^A-Za-z]/g,
  // Accept symbols with at least 5 uppercase letters (forex + common crypto tickers).
  symbol: /^[A-Z]{5,}$/,
  // Profit numbers like -446.22 or 5963.09 (ignore currency formatting).
  profitNumber: /[+\-−]?\s*\d[\d,]*\.?\d*/,

  // Profit cell includes a currency suffix, e.g. "-28.93 USD" or "+6.14 JPY"
  profitCellWithCurrency: /([+\-−])?\s*(\d[\d,]*\.?\d*)\s*([A-Z]{3})\b/i
};

let lastNoRootLogAt = 0;
let lastSignature = null;
let lastModel = null;
let lastUpdatedAt = null;
let pollIntervalId = null;

function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
  return el.getClientRects().length > 0;
}

function cleanSymbol(rawText) {
  const cleaned = String(rawText ?? "")
    .replace(REGEX.symbolLettersOnly, "")
    .toUpperCase();
  if (!REGEX.symbol.test(cleaned)) return null;
  return cleaned;
}

function parseSignedNumber(rawText) {
  const text = String(rawText ?? "").trim().replace("−", "-").replace(/,/g, "");
  const match = text.match(/^([+\-])\s*(\d[\d]*\.?\d*)/);
  if (!match) return null;
  const sign = match[1];
  const value = Number(match[2]);
  if (Number.isNaN(value)) return null;
  return sign === "-" ? -Math.abs(value) : Math.abs(value);
}

function describeEl(el) {
  if (!el) return "null";
  const cls = (el.className && typeof el.className === "string") ? el.className.trim().split(/\s+/)[0] : "";
  return `${el.tagName}${cls ? "." + cls : ""}`;
}

function extractSymbolFallbackFromRow(rowEl) {
  const nodes = Array.from(rowEl.querySelectorAll("td, span, div")).filter((n) => isVisible(n));
  for (const node of nodes) {
    const symbol = cleanSymbol(node.textContent);
    if (symbol) return symbol;
  }
  return null;
}

function getOpenPositionsTableRoot() {
  // Find the table/grid that contains the visible Profit column cells.
  // We intentionally avoid TradingView hashed class names and prefer stable attributes.
  const profitCells = Array.from(document.querySelectorAll('td[data-label="Profit"]'))
    .filter(isVisible);

  if (!profitCells.length) return null;

  // Choose the deepest common "table-like" ancestor with the most Profit cells.
  const counts = new Map(); // el -> count
  for (const td of profitCells) {
    const tableLike =
      td.closest("table") ||
      td.closest('[role="table"]') ||
      td.closest('[role="grid"]') ||
      td.closest("div");
    if (!tableLike) continue;
    counts.set(tableLike, (counts.get(tableLike) || 0) + 1);
  }

  let best = null;
  let bestCount = 0;
  for (const [el, cnt] of counts.entries()) {
    // Prefer tables in the lower half of the viewport (broker panel).
    const rect = el.getBoundingClientRect();
    const inLowerHalf = rect.top > window.innerHeight * 0.35;
    const score = cnt + (inLowerHalf ? 2 : 0);
    if (score > bestCount) {
      bestCount = score;
      best = el;
    }
  }

  return best;
}

function extractOpenPositionRows() {
  const root = getOpenPositionsTableRoot();
  if (!root) {
    const now = Date.now();
    if (now - lastNoRootLogAt > 5000) {
      console.warn(`${DEBUG_PREFIX} open positions table not found yet`);
      lastNoRootLogAt = now;
    }
    return [];
  }

  const profitTds = Array.from(root.querySelectorAll('td[data-label="Profit"]')).filter(isVisible);
  const rowEls = Array.from(
    new Set(
      profitTds
        .map((td) => td.closest("tr") || td.parentElement)
        .filter((el) => el && isVisible(el))
    )
  );

  const rows = [];

  for (const rowEl of rowEls) {
    const profitTd = rowEl.querySelector('td[data-label="Profit"]');
    if (!profitTd) continue;

    // Symbol is in its own td if present; otherwise find it within the same row.
    const symbolTd = rowEl.querySelector('td[data-label="Symbol"]');
    const symbolFromTd = symbolTd ? symbolTd.textContent.trim() : null;
    const symbol = cleanSymbol(symbolFromTd) || extractSymbolFallbackFromRow(rowEl);
    if (!symbol) continue;

    const profitSpans = Array.from(profitTd.querySelectorAll("span")).map((s) =>
      (s.textContent || "").trim()
    );

    // Profit numeric is the first signed numeric span (currency is a separate span).
    const numericSpan = profitSpans.find((t) => /[+\-−]\s*\d/.test(t));
    if (!numericSpan) continue;

    const profit = parseSignedNumber(numericSpan);
    if (profit === null) continue;

    rows.push({ symbol, profit });
  }

  return rows;
}

function groupByQuoteCurrency(rows) {
  const map = new Map(); // quote -> group

  for (const row of rows) {
    if (!row?.symbol) continue;
    if (typeof row.profit !== "number" || Number.isNaN(row.profit)) continue;
    const quote = extractQuoteCurrency(row.symbol);

    if (!map.has(quote)) {
      map.set(quote, {
        currency: quote,
        totalProfit: 0,
        count: 0,
        pairsMap: new Map() // symbol -> { totalProfit, count, positions[] }
      });
    }

    const group = map.get(quote);
    group.totalProfit += row.profit;
    group.count += 1;

    if (!group.pairsMap.has(row.symbol)) {
      group.pairsMap.set(row.symbol, { symbol: row.symbol, totalProfit: 0, count: 0, positions: [] });
    }
    const pairAgg = group.pairsMap.get(row.symbol);
    pairAgg.totalProfit += row.profit;
    pairAgg.count += 1;
    pairAgg.positions.push({ profit: row.profit });
  }

  const groups = Array.from(map.values()).map((g) => {
    const pairs = Array.from(g.pairsMap.values())
      .map((p) => ({
        symbol: p.symbol,
        totalProfit: p.totalProfit,
        count: p.count,
        positions: (p.positions || []).slice().sort((a, b) => (a.profit ?? 0) - (b.profit ?? 0))
      }))
      .sort((a, b) => a.totalProfit - b.totalProfit); // worst first

    return {
      currency: g.currency,
      totalProfit: g.totalProfit,
      count: g.count,
      pairs
    };
  });

  // Sort by worst PnL first (most negative).
  groups.sort((a, b) => a.totalProfit - b.totalProfit);
  return groups;
}

function computeSignature(rows) {
  // Basic change detector: stable-ish signature based on sorted symbols + profit values.
  // Avoid JSON.stringify on large objects.
  const parts = rows
    .map((r) => `${r.symbol}:${Math.round((r.profit || 0) * 100)}`)
    .sort();
  return parts.join("|");
}

function ensureOverlay() {
  // Prevent duplicate injection on TradingView SPA route changes.
  if (document.getElementById("tv-overlay-panel")) {
    if (!overlayInstance) {
      overlayInstance = new window.OverlayView({ parent: document.body });
      const ok = overlayInstance.attach?.();
      if (!ok) {
        document.getElementById("tv-overlay-panel")?.remove();
        overlayInstance = null;
        ensureOverlay();
      }
    }
    return;
  }

  const OverlayView = window.OverlayView;
  if (typeof OverlayView !== "function") {
    console.warn("[TradingView Overlay] OverlayView not found on window");
    return;
  }

  overlayInstance = new OverlayView({ parent: document.body });
  overlayInstance.init();

  // Placeholder until extraction works.
  overlayInstance.setModel(null, null);
}

ensureOverlay();

function runUpdate() {
  if (!overlayInstance) {
    ensureOverlay();
    if (!overlayInstance) return;
  }

  const tableRoot = getOpenPositionsTableRoot();
  const rows = extractOpenPositionRows();
  const stale = rows.length === 0 && Boolean(lastModel);

  // Keep the last valid dataset if broker panel is minimized/hidden.
  if (stale) {
    overlayInstance.setModel(lastModel, lastUpdatedAt, {
      stale: true,
      hiddenReason: "Broker panel hidden"
    });
    return;
  }

  if (!tableRoot && !lastModel) {
    overlayInstance.setModel({ currencyGroups: [] }, new Date(), {
      stale: false,
      hiddenReason: "Unable to read positions"
    });
    return;
  }

  const signature = computeSignature(rows);
  if (signature === lastSignature) return;
  lastSignature = signature;

  const currencyGroups = groupByQuoteCurrency(rows);
  lastModel = { currencyGroups };
  lastUpdatedAt = new Date();

  overlayInstance.setModel(lastModel, lastUpdatedAt, {
    stale: false,
    hiddenReason: ""
  });
}

function stopLoop() {
  if (pollIntervalId !== null) {
    clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
}

function startLoop() {
  stopLoop();
  runUpdate();
  pollIntervalId = setInterval(runUpdate, 1000);
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") startLoop();
  else stopLoop();
});

if (document.visibilityState === "visible") startLoop();
else stopLoop();

})();

export function extractQuoteCurrency(symbol) {
  if (!symbol || typeof symbol !== "string") return "OTHER";

  // crypto quotes
  const cryptoQuotes = ["USDT", "USDC", "BUSD"];
  for (const q of cryptoQuotes) {
    if (symbol.endsWith(q)) return q;
  }

  // forex (6 chars like EURUSD)
  if (/^[A-Z]{6}$/.test(symbol)) {
    return symbol.slice(-3);
  }

  // fallback
  if (symbol.length >= 5) {
    return symbol.slice(-3);
  }

  return "OTHER";
}

export function aggregateByCurrency(rows) {
  const map = {};

  for (const r of rows) {
    const currency = r.currency || "OTHER";
    const pnl = Number(r.pnl) || 0;

    if (!map[currency]) {
      map[currency] = { pnl: 0, count: 0 };
    }

    map[currency].pnl += pnl;
    map[currency].count += 1;
  }

  return map;
}

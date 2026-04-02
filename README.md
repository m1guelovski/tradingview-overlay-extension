# Currency Exposure

Production-ready Chrome Extension (Manifest V3) for TradingView that overlays live open-position exposure grouped by quote currency.

## Why use this?

TradingView does not show your exposure grouped by currency.

Currency Exposure solves that by helping you instantly:

* identify your biggest losing currencies
* detect concentration risk
* expand into pairs and individual open positions
* make faster risk-management decisions

## What It Does

- Injects a compact floating panel on TradingView pages.
- Reads data from the lower broker **Open Positions** table only.
- Aggregates PnL by quote currency (e.g. `JPY`, `USD`, `USDT`, `USDC`, `BUSD`, `OTHER`).
- Supports drill-down hierarchy:
  - Currency
  - Pair
  - Individual positions
- Updates automatically every 1000 ms.
- Preserves last valid data when broker panel is hidden (stale mode).

## Key Features

- Manifest V3 architecture with modular content scripts.
- Robust extraction based on `td[data-label="Profit"]` and symbol parsing.
- Forex + common crypto quote parsing:
  - `USDT`, `USDC`, `BUSD`
  - Standard forex symbols (`length === 6` -> last 3)
  - Fallback `OTHER`
- Clean dark UI with compact grid alignment.
- Row interactions:
  - Click currency row to expand/collapse pairs.
  - Click pair row to expand/collapse positions.
- Panel interactions:
  - Drag
  - Minimize
  - Close (hide) + reopen button
  - Manual resize from bottom-right corner
- Persistent UI state (`chrome.storage.local`):
  - Position
  - Minimized state
  - Size (width/height)

## Project Structure

```text
manifest.json
src/
  content/
    contentScript.js
    overlay/
      OverlayView.js
      overlayStyles.css
```

## Local Installation (Chrome)

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select this project folder
5. Open TradingView and verify the overlay is visible

## Notes

- Data source is intentionally limited to the TradingView broker Open Positions table.
- No strategy-specific risk rules are applied in the extension.
- If the broker panel is hidden/minimized, the UI keeps last known values and marks timestamp as stale.

## Publishing Checklist (Chrome Web Store)

- [ ] Confirm extension name/version in `manifest.json`
- [ ] Provide extension icons (`16/48/128`) and screenshots
- [ ] Validate behavior on multiple TradingView layouts
- [ ] Review privacy statement (no external data collection)
- [ ] Package and upload through Chrome Web Store Developer Dashboard

## Disclaimer

This extension is provided for informational purposes only and does not constitute financial advice.

## Support

If Currency Exposure helps you, you can support the project here:

https://buymeacoffee.com/m1guelovski


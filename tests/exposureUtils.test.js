import { describe, it, expect } from "vitest";
import { extractQuoteCurrency, aggregateByCurrency } from "../src/utils/exposureUtils.js";

describe("extractQuoteCurrency", () => {
  it("handles forex", () => {
    expect(extractQuoteCurrency("EURUSD")).toBe("USD");
    expect(extractQuoteCurrency("GBPJPY")).toBe("JPY");
  });

  it("handles crypto", () => {
    expect(extractQuoteCurrency("BTCUSDT")).toBe("USDT");
    expect(extractQuoteCurrency("ETHUSDC")).toBe("USDC");
  });

  it("handles edge cases", () => {
    expect(extractQuoteCurrency("")).toBe("OTHER");
    expect(extractQuoteCurrency(null)).toBe("OTHER");
    expect(extractQuoteCurrency("ABC")).toBe("OTHER");
  });
});

describe("aggregateByCurrency", () => {
  it("aggregates pnl correctly", () => {
    const rows = [
      { currency: "USD", pnl: -100 },
      { currency: "USD", pnl: 50 },
      { currency: "JPY", pnl: -30 }
    ];

    const result = aggregateByCurrency(rows);

    expect(result["USD"].pnl).toBe(-50);
    expect(result["USD"].count).toBe(2);
    expect(result["JPY"].pnl).toBe(-30);
  });

  it("handles empty input", () => {
    expect(aggregateByCurrency([])).toEqual({});
  });
});

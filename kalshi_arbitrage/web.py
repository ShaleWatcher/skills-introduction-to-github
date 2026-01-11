from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .backtest import compute_backtest_summary
from .execution import KalshiAuth, KalshiClient
from .signals import compute_lock_spread_signals


HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Kalshi BTC 15m Dashboard</title>
    <style>
      body { font-family: -apple-system, system-ui, Arial, sans-serif; margin: 16px; color: #111; }
      .row { display: flex; gap: 16px; flex-wrap: wrap; }
      .card { border: 1px solid #ddd; border-radius: 10px; padding: 12px; flex: 1 1 420px; }
      h1 { font-size: 18px; margin: 0 0 8px; }
      h2 { font-size: 14px; margin: 0 0 8px; color: #333; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border-bottom: 1px solid #eee; padding: 8px; text-align: left; font-size: 12px; }
      th { background: #fafafa; position: sticky; top: 0; }
      .muted { color: #666; font-size: 12px; }
      .ok { color: #0a7; font-weight: 600; }
      .bad { color: #a00; font-weight: 600; }
      button { padding: 6px 10px; border-radius: 8px; border: 1px solid #ccc; background: #fff; }
      input { padding: 6px 8px; border-radius: 8px; border: 1px solid #ccc; width: 90px; }
      .pill { display:inline-block; padding: 2px 8px; border-radius: 999px; background:#f2f2f2; font-size: 12px; }
      .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
      .kv { border: 1px solid #eee; border-radius: 8px; padding: 8px; }
      .kv b { display:block; font-size: 12px; color:#444; }
      .kv span { font-size: 14px; }
      .topbar { display:flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
    </style>
  </head>
  <body>
    <div class="topbar">
      <h1>Kalshi BTC 15-minute: signals + backtest</h1>
      <div class="muted">
        <span class="pill" id="mode"></span>
        <span class="pill">auto-refresh <span id="refresh">10</span>s</span>
        <span class="pill">series <span id="series"></span></span>
      </div>
    </div>
    <div class="row">
      <div class="card">
        <h2>Live “lock spread” opportunities (BUY YES + BUY NO)</h2>
        <div class="muted">Rule: execute only when asks sum &lt; 1 after fees. Rare in efficient markets.</div>
        <div style="height: 8px"></div>
        <table>
          <thead>
            <tr>
              <th>ticker</th>
              <th>close</th>
              <th>YES</th>
              <th>NO</th>
              <th>profit/pair</th>
              <th>max pairs</th>
              <th>execute</th>
            </tr>
          </thead>
          <tbody id="signals"></tbody>
        </table>
      </div>
      <div class="card">
        <h2>Backtest summary (historical)</h2>
        <div class="muted">This backtest counts only truly risk-free cases for a single market (crossed book).</div>
        <div style="height: 8px"></div>
        <div class="grid" id="bt"></div>
        <div style="height: 8px"></div>
        <div class="muted" id="bt_range"></div>
      </div>
    </div>
    <script>
      const qs = new URLSearchParams(window.location.search);
      const SERIES = qs.get("series") || "KXBTC15M";
      const LOOKAHEAD = parseInt(qs.get("lookahead") || "240", 10);
      const FEE = parseFloat(qs.get("fee") || "0.01");
      const MIN_PROFIT = parseFloat(qs.get("min_profit") || "0.01");
      const DEPTH = parseInt(qs.get("depth") || "1", 10);
      const LOOKBACK_MIN = parseInt(qs.get("lookback") || "1440", 10);
      const REFRESH_S = parseInt(qs.get("refresh") || "10", 10);

      document.getElementById("refresh").textContent = REFRESH_S;
      document.getElementById("series").textContent = SERIES;

      async function load() {
        const url = `/api/state?series=${encodeURIComponent(SERIES)}&lookahead=${LOOKAHEAD}&fee=${FEE}&min_profit=${MIN_PROFIT}&depth=${DEPTH}&lookback=${LOOKBACK_MIN}`;
        const resp = await fetch(url);
        const data = await resp.json();

        document.getElementById("mode").textContent = data.execution_enabled ? `EXECUTION ENABLED (${data.execution_mode})` : "paper mode (no execution)";
        document.getElementById("mode").className = data.execution_enabled ? "pill ok" : "pill";

        const tbody = document.getElementById("signals");
        tbody.innerHTML = "";
        if (!data.signals.length) {
          const tr = document.createElement("tr");
          tr.innerHTML = `<td colspan="7" class="muted">no signals</td>`;
          tbody.appendChild(tr);
        } else {
          for (const s of data.signals) {
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td>${s.ticker}</td>
              <td>${s.close_time || "-"}</td>
              <td>${s.yes_limit.toFixed(4)}</td>
              <td>${s.no_limit.toFixed(4)}</td>
              <td class="${s.expected_profit_per_pair > 0 ? "ok" : "bad"}">${s.expected_profit_per_pair.toFixed(4)}</td>
              <td>${s.max_pairs_at_top}</td>
              <td>
                <input id="qty_${s.ticker}" type="number" min="1" max="${s.max_pairs_at_top}" value="${Math.min(1, s.max_pairs_at_top)}"/>
                <button onclick="execTrade('${s.ticker}')">Trade</button>
              </td>`;
            tbody.appendChild(tr);
          }
        }

        const bt = data.backtest;
        const grid = document.getElementById("bt");
        grid.innerHTML = "";
        const kvs = [
          ["markets scanned", bt.markets_scanned],
          ["signals", bt.signals],
          ["wins", bt.wins],
          ["losses", bt.losses],
          ["total profit", `$${bt.total_profit.toFixed(4)}`],
          ["avg profit", bt.avg_profit === null ? "-" : `$${bt.avg_profit.toFixed(6)}`],
          ["min profit", bt.min_profit === null ? "-" : `$${bt.min_profit.toFixed(6)}`],
          ["max profit", bt.max_profit === null ? "-" : `$${bt.max_profit.toFixed(6)}`],
        ];
        for (const [k,v] of kvs) {
          const div = document.createElement("div");
          div.className = "kv";
          div.innerHTML = `<b>${k}</b><span>${v}</span>`;
          grid.appendChild(div);
        }
        document.getElementById("bt_range").textContent = `UTC range: ${data.backtest_range}`;
      }

      async function execTrade(ticker) {
        const qty = parseInt(document.getElementById(`qty_${ticker}`).value || "0", 10);
        if (!qty || qty <= 0) return alert("qty must be > 0");
        if (!confirm(`Execute lock-spread: BUY YES + BUY NO\\nTicker: ${ticker}\\nQty: ${qty}`)) return;
        const resp = await fetch("/api/execute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ticker, qty, series: SERIES, fee: FEE, min_profit: MIN_PROFIT, depth: DEPTH })
        });
        const data = await resp.json();
        if (!resp.ok) {
          alert(`Execution failed: ${data.error || resp.status}`);
        } else {
          alert(`Execution response:\\n${JSON.stringify(data, null, 2)}`);
        }
      }

      load();
      setInterval(load, REFRESH_S * 1000);
    </script>
  </body>
</html>
"""


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "kalshi-arb/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            series = (qs.get("series", ["KXBTC15M"])[0]).strip()
            lookahead = int(qs.get("lookahead", ["240"])[0])
            fee = float(qs.get("fee", ["0.01"])[0])
            min_profit = float(qs.get("min_profit", ["0.01"])[0])
            depth = int(qs.get("depth", ["1"])[0])
            lookback = int(qs.get("lookback", ["1440"])[0])

            signals = compute_lock_spread_signals(
                series_ticker=series,
                lookahead_minutes=lookahead,
                fee_per_contract=fee,
                min_profit_per_pair=min_profit,
                depth=depth,
            )

            end_ts = int(time.time())
            start_ts = end_ts - lookback * 60
            bt = compute_backtest_summary(
                series_ticker=series,
                start_ts=start_ts,
                end_ts=end_ts,
                fee_per_contract=fee,
                min_profit_per_pair=min_profit,
            )

            auth = KalshiAuth.from_env()
            execution_enabled = bool(os.environ.get("KALSHI_ENABLE_EXECUTION", "").strip() == "1") and (auth is not None)
            execution_mode = auth.mode if auth is not None else "disabled"

            # Convert to jsonable dicts
            sig_rows = [
                {
                    "ticker": s.ticker,
                    "close_time": s.close_time,
                    "yes_limit": s.yes_limit,
                    "no_limit": s.no_limit,
                    "expected_profit_per_pair": s.expected_profit_per_pair,
                    "max_pairs_at_top": s.max_pairs_at_top,
                }
                for s in signals
            ]

            _json(
                self,
                200,
                {
                    "series": series,
                    "execution_enabled": execution_enabled,
                    "execution_mode": execution_mode,
                    "signals": sig_rows,
                    "backtest": {
                        "markets_scanned": bt.markets_scanned,
                        "signals": bt.signals,
                        "wins": bt.wins,
                        "losses": bt.losses,
                        "total_profit": bt.total_profit,
                        "avg_profit": bt.avg_profit,
                        "min_profit": bt.min_profit,
                        "max_profit": bt.max_profit,
                    },
                    "backtest_range": f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(start_ts))}Z -> {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(end_ts))}Z",
                },
            )
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/execute":
            self.send_response(404)
            self.end_headers()
            return

        # Safety: execution is disabled unless explicitly enabled + creds present.
        if os.environ.get("KALSHI_ENABLE_EXECUTION", "").strip() != "1":
            return _json(self, 403, {"error": "Execution disabled. Set KALSHI_ENABLE_EXECUTION=1 on the server."})

        auth = KalshiAuth.from_env()
        if auth is None:
            return _json(
                self,
                403,
                {
                    "error": "Execution not configured. Set KALSHI_EXECUTION_MODE=demo (or live) plus KALSHI_ACCESS_KEY and KALSHI_PRIVATE_KEY_PATH."
                },
            )

        # Extra safety: live mode requires explicit acknowledgement.
        if auth.mode == "live" and os.environ.get("KALSHI_CONFIRM_LIVE", "").strip() != "I_UNDERSTAND":
            return _json(
                self,
                403,
                {
                    "error": "Live execution blocked. Set KALSHI_CONFIRM_LIVE=I_UNDERSTAND to allow live orders."
                },
            )

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            ticker = str(payload.get("ticker", "")).strip()
            qty = int(payload.get("qty", 0))
            if not ticker or qty <= 0:
                return _json(self, 400, {"error": "ticker and qty are required"})

            # Place a paired IOC/FOK batch: BUY YES + BUY NO at current best price limits.
            # NOTE: for a single market, this is only "locked" if the book is crossed;
            # otherwise this is effectively buying both sides and guaranteed losing after fees.
            # We *only* allow execution if current signal exists at the moment of clicking.
            series = str(payload.get("series", "KXBTC15M"))
            fee = float(payload.get("fee", 0.01))
            min_profit = float(payload.get("min_profit", 0.01))
            depth = int(payload.get("depth", 1))

            signals = compute_lock_spread_signals(
                series_ticker=series,
                lookahead_minutes=240,
                fee_per_contract=fee,
                min_profit_per_pair=min_profit,
                depth=depth,
            )
            sig = next((s for s in signals if s.ticker == ticker), None)
            if sig is None:
                return _json(self, 409, {"error": "No longer a valid lock-spread signal for that ticker."})
            qty = min(qty, sig.max_pairs_at_top)
            if qty <= 0:
                return _json(self, 409, {"error": "No size available at top-of-book."})

            yes_cents = int(round(sig.yes_limit * 100))
            no_cents = int(round(sig.no_limit * 100))
            if not (1 <= yes_cents <= 99 and 1 <= no_cents <= 99):
                return _json(self, 400, {"error": "Computed limit prices are out of bounds."})

            client = KalshiClient(auth)
            resp = client.batch_create_orders(
                [
                    {
                        "ticker": ticker,
                        "side": "yes",
                        "action": "buy",
                        "count": qty,
                        "type": "limit",
                        "yes_price": yes_cents,
                        "time_in_force": "fill_or_kill",
                    },
                    {
                        "ticker": ticker,
                        "side": "no",
                        "action": "buy",
                        "count": qty,
                        "type": "limit",
                        "no_price": no_cents,
                        "time_in_force": "fill_or_kill",
                    },
                ]
            )
            return _json(self, 200, {"ok": True, "submitted_qty": qty, "signal": sig.__dict__, "response": resp})
        except Exception as e:
            return _json(self, 500, {"error": str(e)})


def main() -> int:
    p = argparse.ArgumentParser(prog="kalshi_arbitrage.web", description="Single-page dashboard for signals + backtest.")
    p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
    p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    args = p.parse_args()

    httpd = HTTPServer((args.host, int(args.port)), Handler)
    print(f"Dashboard running on http://{args.host}:{args.port}/")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


import os
import json
import psycopg2
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()
DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ.get("UPLOAD_API_KEY", "change-this-secret-key")


def get_conn():
    if "sslmode=" in DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(DATABASE_URL, sslmode="require")


class ScbUpload(BaseModel):
    shop_name: str
    file_name: str
    last_updated: str
    total_visitors: int
    payload: dict


@app.on_event("startup")
def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS store_scb_snapshots (
                    shop_name TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    total_visitors INTEGER NOT NULL DEFAULT 0,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
        conn.commit()
    finally:
        conn.close()


@app.post("/api/upload")
def upload_scb(data: ScbUpload, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO store_scb_snapshots (shop_name, file_name, last_updated, total_visitors, payload, synced_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (shop_name) DO UPDATE SET
                    file_name = EXCLUDED.file_name,
                    last_updated = EXCLUDED.last_updated,
                    total_visitors = EXCLUDED.total_visitors,
                    payload = EXCLUDED.payload,
                    synced_at = NOW();
            """, (data.shop_name, data.file_name, data.last_updated, data.total_visitors, json.dumps(data.payload)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    return {"status": "ok"}


@app.get("/api/shops")
def list_shops():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT shop_name, file_name, last_updated, total_visitors, payload
                FROM store_scb_snapshots
                ORDER BY shop_name;
            """)
            rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        conn.close()

    return [
        {
            "shop_name": r[0],
            "file_name": r[1],
            "last_updated": r[2],
            "total_visitors": r[3],
            "payload": r[4] if isinstance(r[4], dict) else json.loads(r[4] or "{}"),
        }
        for r in rows
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Cloud Store Visitor Monitor</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #070b14; color: #f8fafc; margin: 0; padding: 16px; }
    .wrap { max-width: 920px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
    .card { background: #111827; border: 1px solid rgba(148,163,184,0.18); border-radius: 16px; padding: 16px; }
    select, button { background: #1e293b; color: #fff; border: 1px solid rgba(148,163,184,0.3); padding: 8px 12px; border-radius: 10px; font-size: 14px; }
    .shop { font-size: 26px; font-weight: 800; color: #34d399; }
    .count { font-size: 48px; font-weight: 800; margin: 8px 0; }
    .chart { display: flex; align-items: flex-end; gap: 8px; height: 130px; overflow-x: auto; padding-top: 14px; }
    .bar-col { min-width: 34px; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
    .bar { width: 22px; background: #10b981; border-radius: 5px 5px 0 0; }
    .lbl { font-size: 10px; color: #94a3b8; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: Consolas, monospace; }
    th, td { padding: 8px; border-bottom: 1px solid rgba(148,163,184,0.12); text-align: left; }
    .tbl-wrap { overflow-x: auto; }
    pre { background: #050811; padding: 12px; border-radius: 10px; overflow-x: auto; font-size: 12px; max-height: 360px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;">Select Store</div>
        <select id="shopSelect" onchange="renderSelected()"></select>
      </div>
      <button onclick="fetchShops()">Refresh</button>
    </div>

    <div class="card">
      <div class="shop" id="shopName">Waiting for store sync...</div>
      <div style="font-size:12px;color:#94a3b8;" id="metaInfo">--</div>
      <div class="count" id="totalVisitors">0</div>
      <div style="font-size:12px;color:#38bdf8;">Total Visitors Today (CNL1)</div>
    </div>

    <div class="card">
      <div style="font-weight:700;margin-bottom:8px;">Traffic Graph</div>
      <div class="chart" id="chart"></div>
    </div>

    <div class="card">
      <div style="font-weight:700;margin-bottom:8px;">All .SCB Counter Rows</div>
      <div class="tbl-wrap"><table><thead id="thead"></thead><tbody id="tbody"></tbody></table></div>
    </div>

    <div class="card">
      <div style="font-weight:700;margin-bottom:8px;">Complete .SCB File Content</div>
      <pre id="rawBox">--</pre>
    </div>
  </div>

  <script>
    let allShops = [];

    async function fetchShops() {
      const meta = document.getElementById("metaInfo");
      try {
        const res = await fetch("/api/shops?t=" + Date.now(), { cache: "no-store" });
        if (!res.ok) {
          if (meta) meta.textContent = "API HTTP Error: " + res.status;
          return;
        }
        const data = await res.json();
        allShops = Array.isArray(data) ? data : [];

        if (allShops.length === 0) {
          if (meta) meta.textContent = "No store records in database yet.";
          return;
        }

        const sel = document.getElementById("shopSelect");
        const prevName = sel.options[sel.selectedIndex]?.text || "";
        sel.innerHTML = allShops
          .map((s, i) => `<option value="${i}">${s.shop_name ?? "My Store"}</option>`)
          .join("");

        const matchedIdx = allShops.findIndex(s => s.shop_name === prevName);
        sel.value = matchedIdx >= 0 ? String(matchedIdx) : "0";
        renderSelected();
      } catch (err) {
        if (meta) meta.textContent = "Fetch Error: " + err.message;
      }
    }

    function renderSelected() {
      const sel = document.getElementById("shopSelect");
      const idx = parseInt(sel.value || "0", 10) || 0;
      const item = allShops[idx];
      if (!item) return;

      document.getElementById("shopName").textContent = String(item.shop_name ?? "My Store");
      document.getElementById("metaInfo").textContent =
        `File: ${item.file_name ?? "--"} | Updated: ${item.last_updated ?? "--"} | Stores: ${allShops.length}`;
      document.getElementById("totalVisitors").textContent = String(item.total_visitors ?? 0);

      try {
        const rawPayload = item.payload;
        const p = typeof rawPayload === "string"
          ? JSON.parse(rawPayload || "{}")
          : (rawPayload && typeof rawPayload === "object" ? rawPayload : {});

        const pts = Array.isArray(p.chart_points) ? p.chart_points : [];
        const max = Math.max(...pts.map(x => Number(x && x.count) || 0), 1);
        document.getElementById("chart").innerHTML = pts.map(x => {
          const c = Number(x && x.count) || 0;
          const h = c > 0 ? Math.max(Math.round((c / max) * 100), 10) : 4;
          return `<div class="bar-col"><div style="font-size:10px">${c}</div><div class="bar" style="height:${h}%"></div><div class="lbl">${(x && x.time) || ""}</div></div>`;
        }).join("");

        const cols = Array.isArray(p.column_headers) ? p.column_headers : [];
        const rows = Array.isArray(p.data_rows) ? p.data_rows : [];
        document.getElementById("thead").innerHTML = cols.length
          ? "<tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>"
          : "";
        document.getElementById("tbody").innerHTML = rows
          .filter(r => Array.isArray(r))
          .map(r => "<tr>" + r.map(v => `<td>${v}</td>`).join("") + "</tr>")
          .join("");

        document.getElementById("rawBox").textContent = Array.isArray(p.all_lines)
          ? p.all_lines.join("\n")
          : (p.raw_text || "--");
      } catch (err) {
        document.getElementById("metaInfo").textContent += " | Render note: " + err.message;
      }
    }

    fetchShops();
    setInterval(fetchShops, 15000);
  </script>
</body>
</html>"""

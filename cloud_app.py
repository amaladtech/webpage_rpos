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
  <meta name="theme-color" content="#0b1220" />
  <title>ADTECH People Counting Machine</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#08111f; --panel:#111d30; --panel2:#16243a; --line:#263750;
      --text:#edf4ff; --muted:#93a7c2; --accent:#27c6a5; --blue:#55a7ff;
      --good:#35d39a; --warn:#ffbf69; --shadow:0 12px 35px rgba(0,0,0,.22);
    }
    *{box-sizing:border-box}
    body{margin:0;background:radial-gradient(ellipse at top left,#122744 0,#08111f 45%);color:var(--text);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
    button,input,select{font:inherit}
    .shell{max-width:1440px;margin:auto;padding:26px}
    .topbar{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:25px;flex-wrap:wrap}
    .brand{display:flex;align-items:center;gap:13px}
    .logo{width:48px;height:48px;border-radius:15px;background:linear-gradient(135deg,#22c7a5,#2586ee);
      display:grid;place-items:center;font-weight:900;font-size:18px;color:#061321;box-shadow:var(--shadow)}
    .brand h1{font-size:clamp(18px,2.5vw,25px);margin:0;letter-spacing:.2px}
    .brand p{margin:4px 0 0;color:var(--muted);font-size:12px;letter-spacing:1.5px;text-transform:uppercase}
    .actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
    .btn,.search,.select{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:11px;padding:10px 13px}
    .btn{cursor:pointer;transition:.18s ease}.btn:hover{border-color:var(--accent);transform:translateY(-1px)}
    .btn.primary{background:var(--accent);border-color:var(--accent);color:#05231e;font-weight:800}
    .btn.active{border-color:var(--accent);color:var(--accent)}
    .status{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:12px}
    .dot{width:8px;height:8px;border-radius:50%;background:var(--good);box-shadow:0 0 12px var(--good)}
    .dot.off{background:var(--warn);box-shadow:none}
    .welcome{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:10px 0 18px;flex-wrap:wrap}
    .welcome h2{font-size:20px;margin:0 0 5px}.welcome p{color:var(--muted);margin:0;font-size:13px}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
    .card{background:linear-gradient(145deg,rgba(22,36,58,.96),rgba(14,26,43,.96));border:1px solid var(--line);
      border-radius:17px;padding:18px;box-shadow:var(--shadow);min-width:0}
    .metric-head{display:flex;justify-content:space-between;align-items:center;color:var(--muted);font-size:12px}
    .metric-icon{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:#203c55;color:#6de0c5;font-size:17px}
    .metric-value{font-size:clamp(27px,4vw,36px);font-weight:800;letter-spacing:-1px;margin:13px 0 4px}
    .metric-note{font-size:11px;color:var(--muted)}
    .main-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.85fr);gap:14px;margin-top:14px}
    .section-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
    .section-head h3{font-size:15px;margin:0}.section-head small{color:var(--muted)}
    .shop-controls{display:flex;gap:8px;flex-wrap:wrap}
    .search{min-width:180px;max-width:100%;outline:none}.search:focus,.select:focus{border-color:var(--accent)}
    .select{max-width:100%;outline:none}
    .shop-title{font-size:24px;font-weight:800;margin:5px 0 4px;overflow-wrap:anywhere}
    .shop-meta{color:var(--muted);font-size:12px;line-height:1.7}
    .chart{height:190px;display:flex;align-items:end;gap:9px;overflow-x:auto;padding:15px 4px 0}
    .bar-col{min-width:35px;height:100%;display:flex;flex-direction:column;justify-content:end;align-items:center;gap:6px}
    .bar{width:23px;min-height:3px;border-radius:6px 6px 2px 2px;background:linear-gradient(180deg,#36d9b5,#2587ed);transition:height .25s}
    .bar-value,.bar-label{font-size:10px;color:var(--muted);white-space:nowrap}
    .bar-label{max-width:55px;overflow:hidden;text-overflow:ellipsis}
    .empty{color:var(--muted);font-size:13px;padding:28px 8px;text-align:center}
    .table-card{margin-top:14px}
    .table-wrap{overflow:auto;max-height:430px;border:1px solid var(--line);border-radius:12px}
    table{width:100%;border-collapse:collapse;min-width:560px;font-size:12px}
    th,td{padding:12px 13px;text-align:left;border-bottom:1px solid var(--line)}
    th{color:#a9bdd6;background:#142239;position:sticky;top:0;z-index:1;font-weight:650}
    td{color:#dce8f7}tbody tr:hover{background:rgba(85,167,255,.06)}
    .pill{display:inline-flex;padding:4px 8px;border-radius:30px;background:rgba(53,211,154,.12);color:#6be0b5;font-size:10px}
    .raw{display:none;margin-top:14px}.raw pre{white-space:pre-wrap;overflow:auto;max-height:400px;background:#07101d;border:1px solid var(--line);
      border-radius:12px;padding:14px;color:#b9d2ee;font:12px/1.6 Consolas,monospace}
    .footer{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:11px;padding:20px 3px}
    .error{color:#ff9c9c}.muted{color:var(--muted)}
    @media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.main-grid{grid-template-columns:1fr}}
    @media(max-width:560px){.shell{padding:15px}.grid{gap:9px}.card{padding:14px}.metric-value{font-size:27px}.search{min-width:130px;flex:1}.actions{width:100%}.actions .btn{flex:1}}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="logo">AT</div>
        <div><h1>ADTECH People Counting Machine</h1><p>Smart visitor intelligence</p></div>
      </div>
      <div class="actions">
        <span class="status"><span id="statusDot" class="dot off"></span><span id="connectionText">Connecting…</span></span>
        <button class="btn" id="autoBtn" type="button" onclick="toggleAuto()">Auto refresh: ON</button>
        <button class="btn" type="button" onclick="toggleTheme()">◐ Theme</button>
        <button class="btn primary" type="button" onclick="fetchShops()">↻ Refresh now</button>
      </div>
    </header>

    <section class="welcome">
      <div><h2>Visitor overview</h2><p>Monitor your store traffic from anywhere.</p></div>
      <div class="shop-controls">
        <input class="search" id="shopSearch" type="search" placeholder="Search shop…" oninput="filterShops()" aria-label="Search shops" />
        <select class="select" id="shopSelect" onchange="renderSelected()" aria-label="Select shop"><option value="">Select shop</option></select>
      </div>
    </section>

    <section class="grid">
      <article class="card"><div class="metric-head"><span>Total visitors</span><span class="metric-icon">♙</span></div>
        <div class="metric-value" id="totalVisitors">0</div><div class="metric-note">Latest reported counter total</div></article>
      <article class="card"><div class="metric-head"><span>Connected stores</span><span class="metric-icon">▦</span></div>
        <div class="metric-value" id="storeCount">0</div><div class="metric-note">Stores available in dashboard</div></article>
      <article class="card"><div class="metric-head"><span>Last sync</span><span class="metric-icon">◷</span></div>
        <div class="metric-value" id="lastSync" style="font-size:21px">--</div><div class="metric-note">Latest data received from server</div></article>
      <article class="card"><div class="metric-head"><span>Data file</span><span class="metric-icon">▤</span></div>
        <div class="metric-value" id="fileName" style="font-size:18px;overflow-wrap:anywhere">--</div><div class="metric-note">Latest SCB filename</div></article>
    </section>

    <section class="main-grid">
      <article class="card">
        <div class="section-head"><h3>Visitor traffic</h3><small id="chartCaption">Selected store activity</small></div>
        <div class="chart" id="chart"><div class="empty">Waiting for visitor data…</div></div>
      </article>
      <article class="card">
        <div class="section-head"><h3>Selected store</h3><span class="pill" id="storeStatus">Waiting</span></div>
        <div class="shop-title" id="shopName">Waiting for store sync…</div>
        <div class="shop-meta" id="metaInfo">No data received yet.</div>
        <div style="height:1px;background:var(--line);margin:16px 0"></div>
        <div class="section-head"><h3>Quick actions</h3></div>
        <div class="actions">
          <button class="btn" type="button" onclick="downloadCSV()">↓ Export table CSV</button>
          <button class="btn" type="button" onclick="showRaw()">View raw SCB data</button>
        </div>
      </article>
    </section>

    <section class="card table-card">
      <div class="section-head"><h3>SCB counter details</h3><small id="rowCount">0 rows</small></div>
      <div class="table-wrap"><table><thead id="thead"></thead><tbody id="tbody"><tr><td class="muted">No counter data available.</td></tr></tbody></table></div>
    </section>

    <section class="card raw" id="rawSection">
      <div class="section-head"><h3>Complete SCB file content</h3><button class="btn" type="button" onclick="hideRaw()">Close</button></div>
      <pre id="rawBox">No raw data available.</pre>
    </section>

    <footer class="footer"><span>ADTECH · People Counting Machine</span><span id="updatedAt">Waiting for first update</span></footer>
  </main>

<script>
  let allShops = [];
  let autoRefresh = true;
  let timer = null;
  let selectedItem = null;
  let isLight = false;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    })[ch]);
  }
  function setConnection(ok, message) {
    document.getElementById("statusDot").classList.toggle("off", !ok);
    document.getElementById("connectionText").textContent = message;
    document.getElementById("storeStatus").textContent = ok ? "Data connected" : "No connection";
  }
  function toggleAuto() {
    autoRefresh = !autoRefresh;
    document.getElementById("autoBtn").textContent = "Auto refresh: " + (autoRefresh ? "ON" : "OFF");
    if (timer) clearInterval(timer);
    timer = autoRefresh ? setInterval(fetchShops, 15000) : null;
  }
  function toggleTheme() {
    isLight = !isLight;
    document.documentElement.style.setProperty("--bg", isLight ? "#edf3f9" : "#08111f");
    document.documentElement.style.setProperty("--panel", isLight ? "#ffffff" : "#111d30");
    document.documentElement.style.setProperty("--panel2", isLight ? "#f4f8fc" : "#16243a");
    document.documentElement.style.setProperty("--line", isLight ? "#d6e0eb" : "#263750");
    document.documentElement.style.setProperty("--text", isLight ? "#142338" : "#edf4ff");
    document.documentElement.style.setProperty("--muted", isLight ? "#61758e" : "#93a7c2");
    document.body.style.background = isLight ? "#edf3f9" : "radial-gradient(ellipse at top left,#122744 0,#08111f 45%)";
    document.querySelectorAll(".card").forEach(el => { if(isLight) el.style.background="#fff"; else el.style.background=""; });
  }
  function filterShops() {
    const q = document.getElementById("shopSearch").value.toLowerCase();
    const filtered = allShops.filter(s => String(s.shop_name || "").toLowerCase().includes(q));
    fillShopSelect(filtered);
  }
  function fillShopSelect(items) {
    const sel = document.getElementById("shopSelect");
    const previous = selectedItem ? selectedItem.shop_name : sel.value;
    sel.innerHTML = items.map((s, i) => `<option value="${i}">${escapeHtml(s.shop_name || "My Store")}</option>`).join("");
    const found = items.findIndex(s => s.shop_name === previous);
    sel.value = String(found >= 0 ? found : 0);
    if (items.length) renderItem(items[Number(sel.value)]);
    else if (allShops.length) document.getElementById("shopName").textContent = "No matching store";
  }
  async function fetchShops() {
    try {
      const response = await fetch("/api/shops?t=" + Date.now(), {cache:"no-store"});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      allShops = Array.isArray(data) ? data : [];
      document.getElementById("storeCount").textContent = allShops.length;
      setConnection(true, "Server connected");
      if (!allShops.length) {
        document.getElementById("shopName").textContent = "No store records yet";
        document.getElementById("metaInfo").textContent = "Waiting for the first SCB upload.";
        document.getElementById("totalVisitors").textContent = "0";
        document.getElementById("chart").innerHTML = '<div class="empty">No visitor data received yet.</div>';
        return;
      }
      filterShops();
      document.getElementById("updatedAt").textContent = "Dashboard checked: " + new Date().toLocaleString();
    } catch (err) {
      setConnection(false, "Connection error");
      document.getElementById("metaInfo").textContent = "Unable to load data: " + err.message;
    }
  }
  function renderSelected() {
    const visible = allShops.filter(s => String(s.shop_name || "").toLowerCase().includes(document.getElementById("shopSearch").value.toLowerCase()));
    const item = visible[Number(document.getElementById("shopSelect").value)];
    if (item) renderItem(item);
  }
  function renderItem(item) {
    if (!item) return;
    selectedItem = item;
    document.getElementById("shopName").textContent = item.shop_name || "My Store";
    document.getElementById("totalVisitors").textContent = Number(item.total_visitors || 0).toLocaleString();
    document.getElementById("lastSync").textContent = item.synced_at ? new Date(item.synced_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : (item.last_updated || "--");
    document.getElementById("fileName").textContent = item.file_name || "--";
    document.getElementById("metaInfo").textContent = "SCB updated: " + (item.last_updated || "--") + " · File: " + (item.file_name || "--");
    let p = item.payload;
    try { if (typeof p === "string") p = JSON.parse(p || "{}"); } catch(e) { p = {}; }
    p = p && typeof p === "object" ? p : {};
    const points = Array.isArray(p.chart_points) ? p.chart_points : [];
    const max = Math.max(1, ...points.map(x => Number(x && x.count) || 0));
    document.getElementById("chart").innerHTML = points.length ? points.map(point => {
      const count = Number(point && point.count) || 0;
      const height = count > 0 ? Math.max(7, count / max * 100) : 3;
      return `<div class="bar-col"><span class="bar-value">${count}</span><div class="bar" style="height:${height}%"></div><span class="bar-label">${escapeHtml(point.time || point.label || "")}</span></div>`;
    }).join("") : '<div class="empty">No chart points included in this SCB upload.</div>';
    const cols = Array.isArray(p.column_headers) ? p.column_headers : [];
    const rows = Array.isArray(p.data_rows) ? p.data_rows : [];
    document.getElementById("thead").innerHTML = cols.length ? "<tr>" + cols.map(c => `<th>${escapeHtml(c)}</th>`).join("") + "</tr>" : "";
    document.getElementById("tbody").innerHTML = rows.length ? rows.filter(Array.isArray).map(row => "<tr>" + row.map(v => `<td>${escapeHtml(v)}</td>`).join("") + "</tr>").join("") : '<tr><td class="muted">No counter rows included in this upload.</td></tr>';
    document.getElementById("rowCount").textContent = rows.length + " rows";
    document.getElementById("rawBox").textContent = Array.isArray(p.all_lines) ? p.all_lines.join("\n") : (typeof p.raw_text === "string" ? p.raw_text : "No raw SCB text included.");
  }
  function showRaw() { document.getElementById("rawSection").style.display = "block"; document.getElementById("rawSection").scrollIntoView({behavior:"smooth"}); }
  function hideRaw() { document.getElementById("rawSection").style.display = "none"; }
  function downloadCSV() {
    if (!selectedItem) return;
    let p = selectedItem.payload;
    try { if (typeof p === "string") p = JSON.parse(p || "{}"); } catch(e) { p = {}; }
    const rows = Array.isArray(p.data_rows) ? p.data_rows : [];
    const headers = Array.isArray(p.column_headers) ? [p.column_headers] : [];
    const csv = [...headers, ...rows].map(row => (Array.isArray(row) ? row : []).map(v => '"' + String(v ?? "").replace(/"/g,'""') + '"').join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], {type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = (selectedItem.shop_name || "store").replace(/[^a-z0-9_-]/gi,"_") + "_visitors.csv"; a.click();
    URL.revokeObjectURL(url);
  }
  fetchShops();
  timer = setInterval(fetchShops, 15000);
</script>
</body>
</html>"""

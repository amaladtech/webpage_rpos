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
    select, button { background: #1e293b; color: #fff; border: 1px solid rgba(148,163,184,0.3); padding: 8px 12px; border-radius: 10px; font-size: 14px; cursor: pointer; }
    .shop { font-size: 26px; font-weight: 800; color: #34d399; }
    .count { font-size: 48px; font-weight: 800; margin: 8px 0; }
    .chart { display: flex; align-items: flex-end; gap: 8px; height: 130px; overflow-x: auto; padding-top: 14px; }
    .bar-col { min-width: 34px; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }
    .bar { width: 22px; background: #10b981; border-radius: 5px 5px 0 0; }
    .lbl { font-size: 10px; color: #94a3b8; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: Consolas, monospace; }
    th, td { padding: 8px; border-bottom: 1px solid rgba(148,163,184,0.12); text-align: left; }
    .tbl-wrap { overflow-x: auto; }
    pre { background: #050811; padding: 12px; border-radius: 10px; overflow-x: auto; font-size: 12px; max-height: 360px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <div>
        <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;">Select Store</div>
        <select id="shopSelect" onchange="renderSelected()"></select>
      </div>
      <button type="button" onclick="fetchShops()">Refresh</button>
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
    var allShops = [];

    function fetchShops() {
      var meta = document.getElementById("metaInfo");
      fetch("/api/shops?t=" + Date.now(), { cache: "no-store" })
        .then(function(res) {
          if (!res.ok) {
            meta.textContent = "API HTTP Error: " + res.status;
            return null;
          }
          return res.json();
        })
        .then(function(data) {
          if (!data) return;
          allShops = Array.isArray(data) ? data : [];
          if (allShops.length === 0) {
            meta.textContent = "No store records in database yet.";
            return;
          }

          var sel = document.getElementById("shopSelect");
          var prevName = sel.options.length > 0 ? sel.options[sel.selectedIndex].text : "";
          var html = "";
          for (var i = 0; i < allShops.length; i++) {
            var name = allShops[i].shop_name || "My Store";
            html += '<option value="' + i + '">' + name + '</option>';
          }
          sel.innerHTML = html;

          var matched = 0;
          for (var j = 0; j < allShops.length; j++) {
            if (allShops[j].shop_name === prevName) {
              matched = j;
              break;
            }
          }
          sel.value = String(matched);
          renderSelected();
        })
        .catch(function(err) {
          meta.textContent = "Fetch Error: " + err.message;
        });
    }

    function renderSelected() {
      var sel = document.getElementById("shopSelect");
      var idx = parseInt(sel.value || "0", 10) || 0;
      var item = allShops[idx];
      if (!item) return;

      document.getElementById("shopName").textContent = item.shop_name || "My Store";
      document.getElementById("metaInfo").textContent =
        "File: " + (item.file_name || "--") +
        " | Updated: " + (item.last_updated || "--") +
        " | Stores: " + allShops.length;
      document.getElementById("totalVisitors").textContent =
        item.total_visitors !== undefined && item.total_visitors !== null ? String(item.total_visitors) : "0";

      try {
        var p = item.payload;
        if (typeof p === "string") {
          p = JSON.parse(p || "{}");
        }
        if (!p || typeof p !== "object") {
          p = {};
        }

        var pts = Array.isArray(p.chart_points) ? p.chart_points : [];
        var maxVal = 1;
        for (var i = 0; i < pts.length; i++) {
          var cVal = Number(pts[i] && pts[i].count) || 0;
          if (cVal > maxVal) maxVal = cVal;
        }
        var chartHtml = "";
        for (var j = 0; j < pts.length; j++) {
          var c = Number(pts[j] && pts[j].count) || 0;
          var h = c > 0 ? Math.max(Math.round((c / maxVal) * 100), 10) : 4;
          var lbl = (pts[j] && (pts[j].time || pts[j].label)) || "";
          chartHtml += '<div class="bar-col"><div style="font-size:10px">' + c + '</div><div class="bar" style="height:' + h + '%"></div><div class="lbl">' + lbl + '</div></div>';
        }
        document.getElementById("chart").innerHTML = chartHtml;

        var cols = Array.isArray(p.column_headers) ? p.column_headers : [];
        var rows = Array.isArray(p.data_rows) ? p.data_rows : [];
        var theadHtml = "";
        if (cols.length > 0) {
          theadHtml += "<tr>";
          for (var a = 0; a < cols.length; a++) {
            theadHtml += "<th>" + (cols[a] || "") + "</th>";
          }
          theadHtml += "</tr>";
        }
        document.getElementById("thead").innerHTML = theadHtml;

        var tbodyHtml = "";
        for (var r = 0; r < rows.length; r++) {
          if (!Array.isArray(rows[r])) continue;
          tbodyHtml += "<tr>";
          for (var d = 0; d < rows[r].length; d++) {
            tbodyHtml += "<td>" + (rows[r][d] || "") + "</td>";
          }
          tbodyHtml += "</tr>";
        }
        document.getElementById("tbody").innerHTML = tbodyHtml;

        if (Array.isArray(p.all_lines)) {
          document.getElementById("rawBox").textContent = p.all_lines.join("\\n");
        } else if (typeof p.raw_text === "string") {
          document.getElementById("rawBox").textContent = p.raw_text;
        } else {
          document.getElementById("rawBox").textContent = "--";
        }
      } catch (e) {
        document.getElementById("metaInfo").textContent += " | Render note: " + e.message;
      }
    }

    fetchShops();
    setInterval(fetchShops, 15000);
  </script>
</body>
</html>"""

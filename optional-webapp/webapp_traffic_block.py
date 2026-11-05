# 可选组件:把本块插入已有 Flask webapp(路由必须在 if __name__ 守卫之前!)
# 需替换: <SERVER_IP>(串流控制台地址)。访问路径 /<你的KEY>/blender 与 /<你的KEY>/traffic


# ---------- 📊 流量监控页(服务器 + 本机, 2026-10-26) ----------

import threading as _th
from collections import deque as _dq

_traffic_lock = _th.Lock()
_srv_series = {"rx": _dq(maxlen=180), "tx": _dq(maxlen=180)}
_host_series = {"rx": _dq(maxlen=180), "tx": _dq(maxlen=180)}
_host_last = {"ts": 0.0, "rx_total": 0, "tx_total": 0}


def _read_srv_bytes():
    """从 /proc/net/dev 读取除 lo 外所有网卡的累计收发字节。"""
    rx = tx = 0
    with open("/proc/net/dev") as f:
        lines = f.readlines()[2:]
    for line in lines:
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name.strip() == "lo":
            continue
        cols = rest.split()
        rx += int(cols[0])
        tx += int(cols[8])
    return rx, tx


def _srv_sampler():
    prev = _read_srv_bytes()
    while True:
        time.sleep(5)
        try:
            cur = _read_srv_bytes()
            with _traffic_lock:
                _srv_series["rx"].append(round(max(0, cur[0] - prev[0]) / 5))
                _srv_series["tx"].append(round(max(0, cur[1] - prev[1]) / 5))
            prev = cur
        except Exception:
            pass


_th.Thread(target=_srv_sampler, daemon=True).start()


@app.route("/<key>/api/traffic/report", methods=["POST"])
def traffic_report(key):
    if key != KEY:
        abort(404)
    d = request.get_json(silent=True) or {}
    with _traffic_lock:
        _host_series["rx"].append(float(d.get("rx_rate", 0)))
        _host_series["tx"].append(float(d.get("tx_rate", 0)))
        _host_last.update({"ts": time.time(),
                           "rx_total": int(d.get("rx_total", 0)),
                           "tx_total": int(d.get("tx_total", 0))})
    return jsonify({"ok": True})


@app.route("/<key>/api/traffic/status")
def traffic_status(key):
    if key != KEY:
        abort(404)
    with _traffic_lock:
        srv = {k: list(v)[-120:] for k, v in _srv_series.items()}
        host = {k: list(v)[-120:] for k, v in _host_series.items()}
        last = dict(_host_last)
    tunnel = False
    try:
        import requests as _rq
        r = _rq.get("http://127.0.0.1:47989/serverinfo", timeout=2)
        tunnel = (r.status_code == 200)
    except Exception:
        pass
    try:
        srx, stx = _read_srv_bytes()
    except Exception:
        srx = stx = 0
    return jsonify({"server": srv, "host": host,
                    "host_online": (time.time() - last.get("ts", 0)) < 20,
                    "host_rx_total": last.get("rx_total", 0),
                    "host_tx_total": last.get("tx_total", 0),
                    "srv_rx_total": srx, "srv_tx_total": stx,
                    "tunnel": tunnel, "interval": 5})


TRAFFIC_PAGE = """
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>流量监控</title>
<style>{% raw %}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f5f6fa; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #2c3e50; padding: 24px; }
.wrap { max-width: 880px; margin: 0 auto; }
h1 { font-size: 22px; margin-bottom: 4px; }
h1 span { color: #ff4623; }
.sub { color: #7f8c9b; font-size: 13px; margin-bottom: 20px; }
.card { background: #fff; border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card h2 { font-size: 15px; margin-bottom: 4px; color: #34495e; display: flex; align-items: center; gap: 8px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #ccc; flex: none; }
.dot.ok { background: #2ecc71; } .dot.bad { background: #e74c3c; }
.now { display: flex; gap: 24px; margin: 10px 0 6px; font-size: 14px; }
.now b { font-size: 18px; font-variant-numeric: tabular-nums; }
.rx { color: #27ae60; } .tx { color: #ff4623; }
.legend { font-size: 12px; color: #7f8c9b; }
canvas { width: 100%; height: 120px; display: block; }
.steps { font-size: 13px; color: #5d6d7e; line-height: 1.9; }
{% endraw %}</style>
</head>
<body>
<div class="wrap">
  <h1>📈 流量<span>监控</span></h1>
  <div class="sub">服务器(阿里云 /proc/net/dev)与本机(Agent 上报)实时网络吞吐 · 5 秒采样 · 最近 15 分钟</div>

  <div class="card">
    <h2><span class="dot ok" id="d-srv"></span> 服务器 · 阿里云 <SERVER_IP> <span class="legend" style="margin-left:auto" id="srv-tot"></span></h2>
    <div class="now">下载 <b class="rx" id="srv-rx">0 B/s</b> 上传 <b class="tx" id="srv-tx">0 B/s</b></div>
    <canvas id="c-srv" width="840" height="120"></canvas>
  </div>

  <div class="card">
    <h2><span class="dot" id="d-host"></span> 本机 · <你的电脑名> <span class="legend" style="margin-left:auto" id="host-tot"></span></h2>
    <div class="now">下载 <b class="rx" id="host-rx">0 B/s</b> 上传 <b class="tx" id="host-tx">0 B/s</b></div>
    <canvas id="c-host" width="840" height="120"></canvas>
  </div>

  <div class="card">
    <div class="steps">
      串流链路:浏览器 ↔ 阿里云(18080 + UDP 40000)↔ SSH 隧道(22)↔ 本机 Sunshine。
      串流开启时本机上传(视频流)通常 5~30 MB/s;服务器转发流量约等于串流码率。
      frp 隧道状态:<b id="tun" style="color:#e74c3c">检测中…</b>
    </div>
  </div>
</div>
<script>
const base = "{{ base }}";
function fmt(v) {
  if (v >= 1048576) return (v / 1048576).toFixed(2) + " MB/s";
  if (v >= 1024) return (v / 1024).toFixed(1) + " KB/s";
  return Math.round(v) + " B/s";
}
function fmtT(v) {
  if (v >= 1073741824) return (v / 1073741824).toFixed(2) + " GB";
  if (v >= 1048576) return (v / 1048576).toFixed(1) + " MB";
  return (v / 1024).toFixed(0) + " KB";
}
function draw(canvasId, rx, tx) {
  const cv = document.getElementById(canvasId), ctx = cv.getContext("2d");
  const W = cv.width, H = cv.height, pad = 6;
  ctx.clearRect(0, 0, W, H);
  const all = rx.concat(tx);
  const max = Math.max(1024, Math.max.apply(null, all)) * 1.15;
  const n = Math.max(rx.length, tx.length, 2);
  ctx.strokeStyle = "#eef1f6";
  for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(0, H / 4 * i); ctx.lineTo(W, H / 4 * i); ctx.stroke(); }
  function line(arr, color) {
    if (!arr.length) return;
    ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.beginPath();
    arr.forEach((v, i) => {
      const x = pad + (W - 2 * pad) * i / (n - 1);
      const y = H - pad - (H - 2 * pad) * v / max;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  }
  line(rx, "#27ae60"); line(tx, "#ff4623");
}
function refresh() {
  fetch(base + "/api/traffic/status").then(r => r.json()).then(j => {
    const si = j.interval || 5;
    const sr = j.server.rx.slice(-60), st = j.server.tx.slice(-60);
    const hr = j.host.rx.slice(-60), ht = j.host.tx.slice(-60);
    const srvRx = sr.length ? sr[sr.length - 1] : 0, srvTx = st.length ? st[st.length - 1] : 0;
    const hostRx = hr.length ? hr[hr.length - 1] : 0, hostTx = ht.length ? ht[ht.length - 1] : 0;
    document.getElementById("srv-rx").textContent = fmt(srvRx);
    document.getElementById("srv-tx").textContent = fmt(srvTx);
    document.getElementById("host-rx").textContent = fmt(hostRx);
    document.getElementById("host-tx").textContent = fmt(hostTx);
    document.getElementById("srv-tot").textContent = "开机累计 ↓ " + fmtT(j.srv_rx_total || 0) + " · ↑ " + fmtT(j.srv_tx_total || 0);
    document.getElementById("host-tot").textContent = j.host_online
      ? "Agent 在线 · 开机累计 ↓ " + fmtT(j.host_rx_total) + " · ↑ " + fmtT(j.host_tx_total)
      : "Agent 离线(本机 bat 未运行?)";
    document.getElementById("d-srv").className = "dot ok";
    document.getElementById("d-host").className = "dot " + (j.host_online ? "ok" : "bad");
    const tun = document.getElementById("tun");
    tun.textContent = j.tunnel ? "已连通" : "未连通";
    tun.style.color = j.tunnel ? "#27ae60" : "#e74c3c";
    draw("c-srv", sr, st);
    draw("c-host", hr, ht);
  }).catch(() => {});
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


@app.route("/<key>/traffic")
@app.route("/<key>/traffic/")
def traffic_page(key):
    if key != KEY:
        abort(404)
    return render_template_string(TRAFFIC_PAGE, base="/" + key)


@app.route("/<key>/api/traffic/totals")
def traffic_totals(key):
    if key != KEY:
        abort(404)
    rx, tx = _read_srv_bytes()
    return jsonify({"srv_rx_total": rx, "srv_tx_total": tx})

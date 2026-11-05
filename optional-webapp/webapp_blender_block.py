# 可选组件:把本块插入已有 Flask webapp(路由必须在 if __name__ 守卫之前!)
# 需替换: <SERVER_IP>(串流控制台地址)。访问路径 /<你的KEY>/blender 与 /<你的KEY>/traffic


# ---------- 🎮 Blender 串流控制台(本机 Sunshine + moonlight-web 桥, 2026-10-26) ----------

BLENDER_PAGE = """
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Blender 串流控制台</title>
<style>{% raw %}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #f5f6fa; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #2c3e50; padding: 24px; }
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 22px; margin-bottom: 4px; }
h1 span { color: #ff4623; }
.sub { color: #7f8c9b; font-size: 13px; margin-bottom: 20px; }
.card { background: #fff; border-radius: 10px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card h2 { font-size: 15px; margin-bottom: 12px; color: #34495e; }
.row { display: flex; align-items: center; gap: 10px; padding: 7px 0; font-size: 14px; }
.dot { width: 10px; height: 10px; border-radius: 50%; background: #ccc; flex: none; }
.dot.ok { background: #2ecc71; }
.dot.bad { background: #e74c3c; }
.dot.wait { background: #f39c12; }
.hint { color: #95a5a6; font-size: 12px; margin-left: auto; text-align: right; }
.open-btn { display: inline-block; background: #ff4623; color: #fff !important; text-decoration: none; padding: 12px 26px; border-radius: 8px; font-size: 15px; font-weight: bold; }
.open-btn:hover { background: #e03a1b; }
.steps { font-size: 13px; color: #5d6d7e; line-height: 1.9; }
.steps b { color: #2c3e50; }
a { color: #ff4623; }
{% endraw %}</style>
</head>
<body>
<div class="wrap">
  <h1>🎮 Blender <span>串流控制台</span></h1>
  <div class="sub">本机 Sunshine(NVENC)→ 阿里云中继 → 浏览器 Moonlight Web,鼠标直接操作你电脑上的 Blender</div>

  <div class="card">
    <h2>链路状态 <small id="ts" style="color:#b2bec3;font-weight:normal"></small></h2>
    <div class="row"><div class="dot wait" id="d-mws"></div> 串流桥(moonlight-web)<div class="hint" id="h-mws">检测中…</div></div>
    <div class="row"><div class="dot wait" id="d-tun"></div> frp 隧道 → 本机 Sunshine<div class="hint" id="h-tun">检测中…</div></div>
  </div>

  <div class="card">
    <h2>开始串流</h2>
    <a class="open-btn" href="http://<SERVER_IP>:18080" target="_blank">▶ 打开串流控制台(18080)</a>
    <div class="steps" style="margin-top:12px">
      登录账号:<b>admin / <STREAM_PASSWORD></b> —— 打开后点「home-blender」下的 Desktop,即可在浏览器里用鼠标操作本机桌面(含 Blender)。<br>
      控制台也支持 <a href="https://<SERVER_IP>:18080" target="_blank">https 直连</a>(自签名证书,首次需在浏览器里"继续访问")。https 模式延迟更低(WebCodecs 通道)。
    </div>
  </div>

  <div class="card">
    <h2>说明</h2>
    <div class="steps">
      ① 首次配对由 ZCode 完成,后续浏览器直接连。<br>
      ② 串流的是<b>整个桌面</b>,Esc + Shift+Shift 可退出全屏回网页;<br>
      ③ 本机关机 / frpc 断开时,隧道状态点变红,串流不可用;<br>
      ④ Sunshine 管理界面(本机):<b>https://localhost:47990</b>(admin / <STREAM_PASSWORD>)。
    </div>
  </div>
</div>
<script>
const base = "{{ base }}";
function dot(id, ok, hintId, text) {
  const d = document.getElementById(id);
  d.className = "dot " + (ok ? "ok" : "bad");
  document.getElementById(hintId).textContent = text;
}
function refresh() {
  fetch(base + "/api/blender/status").then(r => r.json()).then(j => {
    dot("d-mws", j.mws, "h-mws", j.mws ? "运行中 (18080)" : "未响应");
    dot("d-tun", j.tunnel, "h-tun", j.tunnel ? "已连通 (47984)" : "未连通(检查本机 frpc)");
    document.getElementById("ts").textContent = new Date().toLocaleTimeString();
  }).catch(() => {});
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


@app.route("/<key>/blender")
@app.route("/<key>/blender/")
def blender_page(key):
    if key != KEY:
        abort(404)
    return render_template_string(BLENDER_PAGE, base="/" + key)


@app.route("/<key>/api/blender/status")
def blender_status(key):
    if key != KEY:
        abort(404)
    import requests as _rq
    import urllib3
    urllib3.disable_warnings()
    out = {"mws": False, "tunnel": False}
    try:
        r = _rq.get("http://127.0.0.1:18080", timeout=2)
        out["mws"] = (r.status_code == 200)
    except Exception:
        pass
    try:
        r = _rq.get("https://127.0.0.1:47984/serverinfo", verify=False, timeout=2)
        out["tunnel"] = (r.status_code in (200, 401, 404))
    except Exception:
        pass
    return jsonify(out)

"""本机代理 Agent v2:流量上报 + 远程服务控制(命令轮询)。

流量每 5s POST;命令每 5s GET(webapp 下发启停 Sunshine/frpc),执行结果回传。
与 frpc 隧道无关(直连服务器公网 80)。配合 optional-webapp 的服务控制卡使用。
"""
import subprocess
import sys
import time

import psutil
import requests

KEY = "<访问密钥>"                       # 与 webapp 的 KEY 一致
BASE = "http://<SERVER_IP>/<访问密钥>"        # 服务器 webapp 入口
INTERVAL = 5
SUNSHINE_EXE = r"C:\Program Files\Sunshine\sunshine.exe"
SUNSHINE_CWD = r"C:\Program Files\Sunshine\config"
FRPC_BAT = r"D:\blender-bridge\start-frpc.bat"

CREATE_NO_WINDOW = 0x08000000


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]]", *a, flush=True)


def totals():
    per = psutil.net_io_counters(pernic=True)
    rx = tx = 0
    for name, c in per.items():
        if name.lower().startswith("loopback"):
            continue
        rx += c.bytes_recv
        tx += c.bytes_sent
    return rx, tx


def report_traffic():
    prev = totals()
    while True:
        time.sleep(INTERVAL)
        try:
            cur = totals()
            payload = {
                "rx_rate": max(0, cur[0] - prev[0]) / INTERVAL,
                "tx_rate": max(0, cur[1] - prev[1]) / INTERVAL,
                "rx_total": cur[0],
                "tx_total": cur[1],
            }
            prev = cur
            requests.post(f"{BASE}/api/traffic/report",
                          params={"key": KEY}, json=payload, timeout=8)
        except Exception as e:
            log("traffic failed:", str(e)[:80])


def proc_running(image):
    r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}"],
                       capture_output=True, text=True, encoding="gbk", errors="replace")
    return image.lower() in (r.stdout or "").lower()


def exec_cmd(target, action):
    """执行启停命令,返回 (ok, detail)。权限不足等失败会如实返回。"""
    if target == "frpc":
        if action == "stop":
            r = subprocess.run(["taskkill", "/IM", "frpc.exe", "/F"],
                               capture_output=True, text=True, encoding="gbk", errors="replace")
            ok = r.returncode == 0
            return ok, (r.stdout or r.stderr).strip()[:120]
        if action == "start":
            subprocess.Popen([FRPC_BAT], creationflags=CREATE_NO_WINDOW)
            time.sleep(4)
            return proc_running("frpc.exe"), "frpc 已拉起(start-frpc.bat: ssh隧道+frpc)"
    if target == "sunshine":
        if action == "stop":
            r = subprocess.run(["taskkill", "/IM", "sunshine.exe", "/F"],
                               capture_output=True, text=True, encoding="gbk", errors="replace")
            ok = r.returncode == 0
            detail = (r.stdout or r.stderr).strip()[:120]
            if not ok:
                detail += "(若提示拒绝访问:Sunshine 以管理员运行,需管理员权限才能停止)"
            return ok, detail
        if action == "start":
            try:
                subprocess.Popen([SUNSHINE_EXE], cwd=SUNSHINE_CWD,
                                 creationflags=CREATE_NO_WINDOW)
                time.sleep(4)
                return proc_running("sunshine.exe"), "sunshine 已拉起"
            except Exception as e:
                return False, f"启动失败: {str(e)[:100]}"
    if target == "sunshine_svc":
        flag = "start" if action == "start" else "stop"
        r = subprocess.run(["sc", flag, "sunshinesvc"], capture_output=True, text=True, encoding="gbk", errors="replace")
        return r.returncode == 0, (r.stdout or r.stderr).strip()[:120]
    return False, f"未知命令 {target}/{action}"


def poll_commands():
    last_id = None
    while True:
        time.sleep(INTERVAL)
        try:
            r = requests.get(f"{BASE}/api/blender/agent-cmd",
                             params={"key": KEY}, timeout=8).json()
            cmd = r.get("cmd")
            if not cmd or cmd.get("cmd_id") == last_id:
                continue
            last_id = cmd["cmd_id"]
            log("收到命令:", cmd["target"], cmd["action"])
            ok, detail = exec_cmd(cmd["target"], cmd["action"])
            log("执行结果:", ok, detail)
            requests.post(f"{BASE}/api/blender/agent-result",
                          params={"key": KEY},
                          json={"cmd_id": cmd["cmd_id"], "ok": ok,
                                "detail": detail}, timeout=8)
        except Exception as e:
            log("cmd poll failed:", str(e)[:80])


def main():
    import threading
    threading.Thread(target=report_traffic, daemon=True).start()
    poll_commands()


if __name__ == "__main__":
    main()

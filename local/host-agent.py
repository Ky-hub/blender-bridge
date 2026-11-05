"""本机流量上报 Agent(可选):psutil 采样(排除 loopback),每 5 秒推送到 webapp。

依赖: pip install psutil requests
用法: python host-agent.py   (建议 pythonw + 启动文件夹实现开机自启)
"""
import time

import psutil
import requests

BASE = "http://<SERVER_IP>/<KEY>/api/traffic/report"
INTERVAL = 5


def totals():
    per = psutil.net_io_counters(pernic=True)
    rx = tx = 0
    for name, c in per.items():
        if name.lower().startswith("loopback"):
            continue
        rx += c.bytes_recv
        tx += c.bytes_sent
    return rx, tx


def main():
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
            requests.post(BASE, json=payload, timeout=8)
        except Exception as e:
            print("report failed:", e, flush=True)


if __name__ == "__main__":
    main()

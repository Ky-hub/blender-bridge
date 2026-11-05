@echo off
rem 流量上报 Agent 自启(pythonw 无窗口运行;需先 pip install psutil requests)
start "" /min "<PYTHON路径,如 D:\python\pythonw.exe>" "D:\blender-bridge\host-agent.py"

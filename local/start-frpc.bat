@echo off
rem 开机自启:先起 SSH 隧道,再起 frpc
start "" /min "D:\blender-bridge\ssh-tunnel.bat"
timeout /t 4 >nul
start "" /min "D:\blender-bridge\frp\frp_0.72.0_windows_amd64\frpc.exe" -c "D:\blender-bridge\frp\frpc-ssh.toml"

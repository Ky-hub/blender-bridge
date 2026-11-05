@echo off
rem SSH 本地转发:本机 7000 -> 服务器 127.0.0.1:7000 (frps)
rem 前提:已配 SSH 免密(公钥放服务器 authorized_keys)
:loop
ssh -N -L 7000:127.0.0.1:7000 -o ServerAliveInterval=15 -o ExitOnForwardFailure=yes root@<SERVER_IP>
timeout /t 5 >nul
goto loop

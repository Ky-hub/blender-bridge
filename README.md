# Blender 网页串流桥 · 部署指南

在任意浏览器(手机/平板/电脑)上用鼠标直接操控家里电脑里的 Blender(或整个桌面),画面走家用显卡硬件编码,公网服务器只做转发。

```
浏览器 ──HTTPS(WebSocket/WebRTC)──> 公网服务器(moonlight-web 桥 + frps)
                                          │ frp 隧道(装在 SSH 里,家里零端口暴露)
                                          ▼
                                    家里电脑 Windows(Sunshine 硬件编码推流 → 你的 Blender)
```

**组件一览**

| 组件 | 跑在哪 | 作用 |
|---|---|---|
| Sunshine | 家里电脑 | 采集桌面 + 显卡硬件编码(NVENC/AMF/QSV),Moonlight 协议服务端 |
| frpc | 家里电脑 | 把 Sunshine 的端口映射到服务器的 loopback |
| ssh 隧道 | 家里电脑 | 承载 frp 全部流量(含 UDP),只需服务器 22 端口 |
| frps | 公网服务器 | 隧道对端,在 loopback 上还原出 Sunshine 端口 |
| moonlight-web-stream | 公网服务器 | Moonlight 客户端桥 + HTTPS 网页(浏览器直接连) |
| watchdog | 公网服务器 | 自动清理断线残留的僵尸会话 |
| host-agent(可选) | 家里电脑 | 上报本机流量到状态页 |

**家里电脑零端口暴露**:frpc 和 ssh 都是从家里主动连出去的,路由器不用做任何映射。

---

## 〇、准备条件

- 公网服务器一台(Linux,1核1G 起步,流量转发吃带宽不吃 CPU),本文假设已有 SSH 访问
- 家里电脑 Windows 10/11 + 独立显卡(N 卡 easiest)
- 家里电脑能 SSH 到服务器(推荐配免密:`ssh-keygen` 后把公钥追加到服务器 `/root/.ssh/authorized_keys`)
- 浏览器:Chrome/Edge 系(手机自带 Chrome 也行)。**不要用公司沙箱/隔离浏览器**(会拦 WebRTC 和非标端口)

## 需要替换的变量(全文 `<尖括号>` 占位)

| 占位符 | 说明 | 生成/获取方式 |
|---|---|---|
| `<SERVER_IP>` | 服务器公网 IP | 你自己的 |
| `<FRP_TOKEN>` | frp 通信令牌 | 服务器上 `openssl rand -hex 16` |
| `<STREAM_PASSWORD>` | Sunshine / moonlight-web 登录密码 | 自己定,建议强密码 |
| `<HOST_ID>` | 配对后 moonlight-web 分配的主机 ID | 配对步骤输出 |
| `<PYTHON>` | 家里电脑 Python 解释器(≥3.8,装了 psutil) | 可选组件才需要 |

## 控制台防火墙(云厂商安全组)需要放行

| 协议 | 端口 | 用途 | 必需性 |
|---|---|---|---|
| TCP | 22 | SSH(你本来就要用) | 已有 |
| TCP | 18080 | 串流网页(HTTPS) | **必需** |
| UDP | 40000-40010 | WebRTC 媒体(可选低延迟通道) | 可选 |
| TCP | 7000 | frp 直连(本方案走 SSH,**不需要**开) | 不需要 |

---

## 一、服务器部署

### 1. frps

```bash
mkdir -p /opt/frp && cd /opt/frp
# 直连 GitHub 慢就用镜像: https://gh-proxy.com/https://github.com/...
curl -sLO https://github.com/fatedier/frp/releases/download/v0.72.0/frp_0.72.0_linux_amd64.tar.gz
tar xzf frp_0.72.0_linux_amd64.tar.gz

cat > /opt/frp/frps.toml <<EOF
bindPort = 7000
proxyBindAddr = "127.0.0.1"          # 关键:Sunshine 端口只映射到服务器 loopback,公网不暴露
auth.token = "<FRP_TOKEN>"
EOF
```

`server/frps.service` 内容见本包,拷到 `/etc/systemd/system/` 后:

```bash
systemctl daemon-reload && systemctl enable --now frps
```

### 2. moonlight-web-stream

```bash
mkdir -p /opt/moonlight-web && cd /opt/moonlight-web
curl -sLO https://github.com/MrCreativ3001/moonlight-web-stream/releases/download/v3.0.1/moonlight-web-x86_64-unknown-linux-musl.tar.gz
tar xzf moonlight-web-x86_64-unknown-linux-musl.tar.gz     # 得到 package/web-server + package/static/
chmod +x package/web-server

# 自签名证书(浏览器首次访问需手动接受;SAN 必须含服务器 IP)
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes \
  -subj "/CN=<SERVER_IP>" -addext "subjectAltName=IP:<SERVER_IP>"
```

`server/moonlight-web.service` 内容见本包(把 `<SERVER_IP>` 替换掉),拷到 systemd 后启动:

```bash
systemctl daemon-reload && systemctl enable --now moonlight-web
curl -sk https://127.0.0.1:18080 -o /dev/null -w "%{http_code}\n"   # 应输出 200
```

### 3. 注册管理员

浏览器打开 `https://<SERVER_IP>:18080`(接受自签名证书警告:Android Chrome 可「继续前往」;iOS 需先把证书下载安装并信任)。**第一个注册的账号自动成为管理员**。

> 也可以用 API(用户字段叫 `name`):`curl -X POST http://127.0.0.1:18080/api/users -H "content-type: application/json" -d '{"name":"admin","password":"<STREAM_PASSWORD>"}'`(服务器本机执行)

### 4. 看门狗(强烈建议装)

浏览器直接关标签断开时,Sunshine 会话会残留 `Busy` 状态,导致后续连接全部被拒。`server/watchdog.sh` 每分钟巡检并自动强退僵尸会话(脚本里的 `<HOST_ID>`/`<STREAM_PASSWORD>` 在配对完成后回填)。`server/watchdog.service` + `watchdog.timer` 拷到 systemd 后 `systemctl enable --now watchdog.timer`。

---

## 二、家里电脑部署

### 1. Sunshine

- 安装:`winget install LizardByte.Sunshine`(或官网安装包)
- **用管理员运行安装目录里的 `scripts\install-service.bat` 注册系统服务**(开机自启 + 配置目录可写;直接双击 sunshine.exe 跑的话,配置目录跟随 cwd,Program Files 下不可写会踩坑)
- 浏览器打开 `https://localhost:47990`,首次向导设置账号密码(或命令行 `sunshine.exe --creds <用户名> <密码>`)
- 确认监听端口:47984/47989/47990/48010 (TCP) + 47998/47999/48000 (UDP)

### 2. frp + SSH 隧道(frp-over-SSH,不需要在防火墙开 7000)

`local/frpc-ssh.toml` 替换 `<FRP_TOKEN>` 后放到任意固定目录(示例 `D:\blender-bridge\frp\`)。

`local/ssh-tunnel.bat`:SSH 把家里电脑的 127.0.0.1:7000 转发到服务器的 frps(所以 frpc 连 `127.0.0.1:7000` 就等于连上服务器),断线自动重连。**SSH 必须免密**(公钥已放服务器),否则自启时卡在密码输入。

### 3. 开机自启

把 `local/start-frpc.bat`(先起 ssh 隧道,4 秒后再起 frpc)放入启动文件夹:

```
Win+R → shell:startup → 把 bat 的快捷方式/文件放进去
```

> frpc 有多个版本并存也没关系,跑之前 `taskkill /IM frpc.exe /F` 清一下。

### 4. 验证隧道

在本机跑起来 frpc 后,SSH 到服务器执行:

```bash
curl -s http://127.0.0.1:47989 -o /dev/null -w "%{http_code}\n"   # 应输出 200(穿透到了家里 Sunshine)
```

---

## 三、配对(把 Sunshine 交给 moonlight-web)

登录 moonlight-web 拿会话 cookie 后,在**服务器本机**执行(或浏览器 UI 操作:右键主机 → 配对):

```bash
BASE=http://127.0.0.1:18080
curl -s -c ck -X POST $BASE/api/login -H "content-type: application/json" \
  -d '{"name":"admin","password":"<STREAM_PASSWORD>"}'

# ① 添加主机(立即探测 Sunshine 可达性,不通会报 host not found)
curl -s -b ck -X POST $BASE/api/host -H "content-type: application/json" \
  -d '{"name":"home-blender","address":"127.0.0.1"}'
# → 记下返回的 "host_id"(配对后也可在网页 UI 里看)

# ② 发起配对(流式响应,先吐出 PIN,连接挂起等待)
curl -s -N -b ck -X POST $BASE/api/pair -H "content-type: application/json" \
  -d '{"host_id":<HOST_ID>}'
# → {"Pin":"1234"}  …连接保持中
```

然后在**家里电脑**上把 PIN 填给 Sunshine:

```bash
# 列出待配对请求拿 pairing_id
curl -sk -u admin:<STREAM_PASSWORD> https://localhost:47990/api/pin
# 提交(JSON 三字段缺一不可!)
curl -sk -u admin:<STREAM_PASSWORD> -X POST https://localhost:47990/api/pin \
  -H "content-type: application/json" \
  -d '{"pairing_id":"<上一步返回的32位hex>","pin":"1234","name":"moonlight-web"}'
# → {"status":true} 且 ② 的流式连接返回 {"Paired":{...}} 即成功
```

⚠️ ②的连接挂起最长 150 秒,超时重跑一遍即可(PIN 会变)。

---

## 四、使用

1. 浏览器(Chrome/Edge,**别用公司沙箱浏览器**)打开 `https://<SERVER_IP>:18080`,登录后点你的主机 → **Desktop**
2. 几秒内浏览器里出现家里电脑桌面,鼠标/键盘直接操作;在本机先打开 Blender,网页里直接建模
3. **正确退出**:用串流画面内的退出按钮(菜单 Quit)。直接关标签的话,看门狗会在 1~2 分钟内自动清掉残留会话
4. 手机状态页/流量页(可选组件)见 `optional-webapp/`,需自备一个 Flask 网站集成

---

## 五、串流参数(流量优化)

moonlight-web 的默认参数在 `package/static/index.js`(改前备份):

```js
bitrate:1e4          →  8000            # kbps,桌面/建模 8M 足够,省 20% 流量
fps:60               →  保持 60          # 鼠标手感优先
videoCodec:"h264"    →  保持 h264        # 见下方踩坑①
dataTransport:"auto" →  "websocket"     # 见下方踩坑②
```

> 用户浏览器一旦在设置面板保存过参数(localStorage `mlSettings`),就以保存值为准,需手动改或清站点数据。

---

## 六、踩坑大全(全部实测踩过)

1. **UDP NAT 回收**:手机蜂窝网对高位 UDP 回收激进,WebRTC 会话稳定在 30~70 秒断开 → 解法:HTTPS + 默认 `dataTransport:"websocket"`(纯 TCP,WebCodecs 硬解)。
2. **AV1 别做默认**:服务器/显卡支持 AV1 编码 ≠ 浏览器 WebRTC 支持 AV1 解码。AV1 默认会导致 "failed to add video track … client doesn't support the required codecs" → 全部掉进慢速兜底。默认 H264,AV1 让用户在设置面板自选。
3. **僵尸 Busy 会话**:断开后 Sunshine 残留 Busy,后续连接全被拒("很难连上")→ 看门狗解决;手动清:`POST /api/host/cancel {"host_id":<HOST_ID>}`。
4. **Sunshine 配置目录跟随启动 cwd**:从 Program Files 直接跑、又没有服务权限时,写配置会失败 → 正式部署务必注册系统服务(管理员)。
5. **frps 的 `proxyBindAddr="127.0.0.1"` 必须设**:否则 Sunshine 端口暴露公网。
6. **7000 被云防火墙挡时不用纠结**:frp 整体塞进 SSH(`ssh -N -L 7000:127.0.0.1:7000` + frpc 连 127.0.0.1),22 端口本来就要开。
7. **Moonlight 端口号必须和 frp 映射一一对应**(47984→47984 …),客户端握手时会按固定端口回连。
8. **moonlight-web 的 `/api/pair` 是流式响应**(curl 加 `-N`),PIN 在流里;Sunshine 的 `/api/pin` 必须 JSON 三字段 `{pairing_id,pin,name}`,form 编码会报 Content type mismatch。
9. **Windows 计划任务(schtasks)传参引号地狱**:别跟参数较劲,写个 bat 放 `shell:startup`。
10. **HTTPS 是 WS 传输 WebCodecs 的前提**:纯 HTTP 下 WS 通道会退化为旧式播放,画面极慢。

---

## 七、目录清单

```
├── README.md                 本文档
├── server/                   服务器侧(全部拷到 /etc/systemd/system/ 等位置后按 README 调整)
│   ├── frps.toml
│   ├── frps.service
│   ├── moonlight-web.service
│   ├── watchdog.sh
│   ├── watchdog.service
│   └── watchdog.timer
├── local/                    家里电脑侧
│   ├── frpc-ssh.toml
│   ├── ssh-tunnel.bat
│   ├── start-frpc.bat
│   ├── host-agent.py         可选:流量上报
│   └── start-agent.bat       可选:Agent 自启
└── optional-webapp/          可选:集成进已有 Flask 网站的状态页/流量页
    ├── webapp_blender_block.py
    └── webapp_traffic_block.py
```

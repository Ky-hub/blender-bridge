#!/bin/bash
# 僵尸串流会话看门狗:WebRTC 已断开但 Sunshine 会话仍 Busy → 强制退出
# 需要回填: HOST_ID(配对步骤返回)、STREAM_PASSWORD
COOKIE=/tmp/.mlcookie
BASE=http://127.0.0.1:18080
HOST_ID=<HOST_ID>
USER=admin
PASS="<STREAM_PASSWORD>"

curl -s -m 6 -c $COOKIE -X POST $BASE/api/login -H "content-type: application/json" \
  -d "{\"name\":\"$USER\",\"password\":\"$PASS\"}" > /dev/null

STATE=$(curl -s -m 6 -b $COOKIE "http://127.0.0.1:18080/api/host?host_id=$HOST_ID" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)[\"host\"][\"server_state\"])" 2>/dev/null)

[ "$STATE" != "Busy" ] && exit 0

# Busy:看最后一条 WebRTC 连接状态,若已断开且超过 45 秒仍未清理 → 强退
LINE=$(journalctl -u moonlight-web --no-pager | grep "peer connection state changed" | tail -1)
LAST=$(echo "$LINE" | awk "{print \$NF}")
LOGTS=$(echo "$LINE" | cut -c1-15)
NOW=$(date +%s)
TS=$(date -d "$LOGTS" +%s 2>/dev/null)

if [ "$LAST" = "closed" ] && [ -n "$TS" ] && [ $((NOW - TS)) -ge 45 ]; then
  curl -s -m 10 -b $COOKIE -X POST $BASE/api/host/cancel -H "content-type: application/json" \
    -d "{\"host_id\":$HOST_ID}" > /dev/null
  echo "$(date "+%F %T") watchdog: cancelled orphaned session"
fi

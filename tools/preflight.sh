#!/bin/sh
# Read-only survey. Command presence does not imply package database compatibility.
echo '=== Firmware ==='
cat /etc/openwrt_release
ubus call system board
echo '=== Native APK database ==='
if command -v apk >/dev/null 2>&1 && [ -s /lib/apk/db/installed ]; then
  apk --version
  apk --print-arch
  awk 'BEGIN{RS="";FS="\n"} {p="";v="";a="";for(i=1;i<=NF;i++){if($i~/^P:/)p=substr($i,3);if($i~/^V:/)v=substr($i,3);if($i~/^A:/)a=substr($i,3)}if(p~/^(appcenter|luci-app-nradio-appcenter|luci-base|libc|kernel|lua|opkg)$/)print p,v,a}' /lib/apk/db/installed
fi
echo '=== Legacy opkg ==='
if command -v opkg >/dev/null 2>&1; then
  opkg --version
  opkg print-architecture
  opkg list-installed | grep -E '^(appcenter|luci-app-nradio-appcenter|luci-base|libc|kernel) ' || true
  [ -s /usr/lib/opkg/status ] || echo 'WARNING: opkg database absent/empty; APK dependencies are not automatically visible.'
fi
echo '=== Disk and RAM ==='
df -k /overlay /tmp
grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached):' /proc/meminfo
echo '=== Appcenter API ==='
ubus -v list appcenter
echo '=== Lua and logging ==='
lua -v
lua -e 'for _,m in ipairs({"nixio","luci.dispatcher","luci.model.uci","luci.cbi","luci.jsonc"}) do local ok=pcall(require,m);print(m,ok) end'
for command_name in logger logread logclient; do command -v "$command_name" || true; done
echo '=== Implementation hashes ==='
sha256sum /usr/sbin/appcenter \
  /usr/lib/lua/luci/controller/nradio_adv/appcenter.lua \
  /usr/lib/lua/luci/view/nradio_appcenter/appcenter.htm \
  /usr/lib/lua/luci/dispatcher.lua
echo '=== Appcenter state ==='
ubus call appcenter list '{}'

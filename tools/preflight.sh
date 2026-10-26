#!/bin/sh
# Read-only device survey. No credentials, config export, or changes.
echo '=== Firmware ==='
cat /etc/openwrt_release
ubus call system board
echo '=== Architectures ==='
opkg print-architecture
echo '=== Disk and RAM ==='
df -k /overlay /tmp
grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached):' /proc/meminfo
echo '=== Appcenter API ==='
ubus -v list appcenter
echo '=== Package versions ==='
opkg list-installed | grep -E '^(appcenter|luci-app-nradio-appcenter|luci-base|libc|kernel) '
echo '=== Implementation hashes ==='
sha256sum /usr/sbin/appcenter \
  /usr/lib/lua/luci/controller/nradio_adv/appcenter.lua \
  /usr/lib/lua/luci/view/nradio_appcenter/appcenter.htm
echo '=== Appcenter state ==='
ubus call appcenter list

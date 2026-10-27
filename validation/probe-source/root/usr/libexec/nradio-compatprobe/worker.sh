#!/bin/sh
# Demonstration only: writes one timestamp to tmpfs per interval.
set -eu
interval=${1:-300}
case "$interval" in ''|*[!0-9]*) exit 2 ;; esac
[ "$interval" -ge 60 ] && [ "$interval" -le 3600 ] || exit 2
umask 077
mkdir -p /tmp/nradio-compatprobe
while :; do
	date -u '+%Y-%m-%dT%H:%M:%SZ' > /tmp/nradio-compatprobe/status.new
	mv /tmp/nradio-compatprobe/status.new /tmp/nradio-compatprobe/status
	sleep "$interval"
done

#!/bin/sh
# Only kit-produced, host-inspected unsigned APK v2 files. No scripts execute.
set -eu
[ "$#" -eq 3 ] || { echo 'Usage: sh device-dry-run-apk.sh PACKAGE.apk syntax-check.lua EXPECTED_SHA256'; exit 2; }
package=$1
checker=$2
expected=$3
case "$expected" in ''|*[!0-9a-f]*) echo 'Expected SHA-256 must be lowercase hexadecimal'; exit 2 ;; esac
[ "${#expected}" -eq 64 ] || exit 2
[ -f "$package" ] && [ -f "$checker" ] || exit 2
[ "$(sha256sum "$package" | awk '{print $1}')" = "$expected" ] || { echo 'APK digest mismatch'; exit 2; }
command -v apk >/dev/null 2>&1 || { echo 'Native APK package manager required'; exit 2; }
grep -q "DISTRIB_REVISION='3.0.0.n0.c1-preview'" /etc/openwrt_release || { echo 'Unverified firmware profile: inspect and adapt before use'; exit 2; }
testroot=${NRADIO_TEST_TMPDIR:-/tmp}
testroot=$(cd "$testroot" && pwd -P)
testdir=$(mktemp -d "$testroot/nradio-apk-preflight.XXXXXX")
cleanup() { case "$testdir" in "$testroot"/nradio-apk-preflight.*) rm -rf "$testdir" ;; esac; }
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
echo '=== APK integrity (local unsigned build; no global trust change) ==='
apk --allow-untrusted verify "$package"
tar -xzf "$package" -C "$testdir"
package_name=$(sed -n 's/^pkgname = //p' "$testdir/.PKGINFO")
case "$package_name" in ''|*[!a-z0-9+._-]*) echo 'Invalid Package metadata'; exit 2 ;; esac
echo "=== Package: $package_name ==="
find "$testdir" -type f > "$testdir/.syntax-files"
while IFS= read -r path; do
    case "$path" in
        *.lua) lua "$checker" "$path"; continue ;;
    esac
    magic=$(dd if="$path" bs=2 count=1 2>/dev/null)
    [ "$magic" = '#!' ] || continue
    first=$(head -n 1 "$path")
    case "$first" in
        '#!/bin/sh'|'#!/bin/sh '*|'#!/bin/ash'|'#!/bin/ash '*|'#!/usr/bin/env sh') sh -n "$path"; echo "Shell syntax OK: $path" ;;
        '#!'*) echo "Review interpreter separately: $path"; exit 2 ;;
    esac
done < "$testdir/.syntax-files"
echo '=== Native package database before ==='
sha256sum /lib/apk/db/installed /etc/apk/world > "$testdir/before"
cat "$testdir/before"
rc=0
apk --allow-untrusted --no-network --simulate --no-scripts add --force-reinstall "$package" || rc=$?
sha256sum /lib/apk/db/installed /etc/apk/world > "$testdir/after"
cmp -s "$testdir/before" "$testdir/after" || { echo 'Package database/world changed during simulation'; exit 1; }
[ "$rc" -eq 0 ] || exit "$rc"
echo 'PASS: syntax, APK integrity, native dependency simulation, unchanged database/world; no install performed.'

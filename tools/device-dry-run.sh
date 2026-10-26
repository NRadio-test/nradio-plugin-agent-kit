#!/bin/sh
# Gzip/tar profile only. Inspect archive safety on the host BEFORE upload.
# Does not install the package or invoke appcenter local/install/callback.
set -eu
[ "$#" -eq 2 ] || { echo "Usage: sh device-dry-run.sh PACKAGE.ipk syntax-check.lua"; exit 2; }
package=$1
checker=$2
[ -f "$package" ] && [ -f "$checker" ] || { echo 'Missing package or Lua checker.' >&2; exit 2; }
testroot=${NRADIO_TEST_TMPDIR:-/tmp}
testroot=$(cd "$testroot" && pwd -P)
testdir=$(mktemp -d "$testroot/nradio-syntax.XXXXXX")
cleanup() {
  case "$testdir" in "$testroot"/nradio-syntax.*) rm -rf "$testdir" ;; esac
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
mkdir "$testdir/data" "$testdir/control"
tar -xzf "$package" -C "$testdir"
tar -xzf "$testdir/data.tar.gz" -C "$testdir/data"
tar -xzf "$testdir/control.tar.gz" -C "$testdir/control"
echo '=== Package control ==='
cat "$testdir/control/control"
package_name=$(sed -n 's/^Package:[[:space:]]*//p' "$testdir/control/control")
case "$package_name" in ''|*[!a-zA-Z0-9+._-]*) echo 'Invalid or duplicate Package field.' >&2; exit 2 ;; esac
echo '=== Maintenance script syntax (not executed) ==='
for name in preinst postinst prerm postrm; do
  f=$testdir/control/$name
  [ -f "$f" ] || continue
  sh -n "$f"
  echo "Shell syntax OK: $f"
done
echo '=== Payload script syntax ==='
find "$testdir/data" -type f > "$testdir/files"
while IFS= read -r f; do
  case "$f" in
    *.lua) lua "$checker" "$f"; continue ;;
  esac
  magic=$(dd if="$f" bs=2 count=1 2>/dev/null)
  if [ "$magic" = '#!' ]; then
    first=$(head -n 1 "$f")
    case "$first" in
      '#!/bin/sh'|'#!/bin/sh '*|'#!/bin/ash'|'#!/bin/ash '*|'#!/usr/bin/env sh')
        sh -n "$f"; echo "Shell syntax OK: $f" ;;
      '#!/usr/bin/lua'|'#!/usr/bin/lua '*|'#!/usr/bin/env lua') lua "$checker" "$f" ;;
      *) echo "Unsupported interpreter; review separately: $f" >&2; exit 2 ;;
    esac
  else
    case "$f" in
      *.sh|"$testdir/data/etc/init.d/"*) sh -n "$f"; echo "Shell syntax OK: $f" ;;
    esac
  fi
done < "$testdir/files"
echo '=== Installed state before dry-run ==='
opkg status "$package_name" > "$testdir/status-before" 2>/dev/null || true
echo '=== opkg noaction ==='
if opkg --noaction --force-reinstall install "$package"; then
  noaction_rc=0
else
  noaction_rc=$?
fi
echo '=== Installed state after dry-run ==='
opkg status "$package_name" > "$testdir/status-after" 2>/dev/null || true
if [ "$(cat "$testdir/status-before")" != "$(cat "$testdir/status-after")" ]; then
  echo 'Package status changed during dry-run; investigate before continuing.' >&2
  exit 1
fi
[ "$noaction_rc" -eq 0 ] || exit "$noaction_rc"
if grep -q '^Status:.* installed' "$testdir/status-before"; then
  echo "Package status unchanged: $package_name was already installed."
else
  echo "Package status unchanged: $package_name remains uninstalled."
fi

#!/usr/bin/env bash
# OfficeCLI bootstrap (Linux / macOS). Reads officecli.lock.json, downloads the
# pinned release asset, verifies SHA-256, installs to tools/officecli/bin/.
# The binary is gitignored on purpose (~32 MB). Run this after cloning.
#
# Usage:
#   bash tools/officecli/install.sh
#   FORCE=1 bash tools/officecli/install.sh   # reinstall even if hash matches
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lock="$root/officecli.lock.json"
[ -f "$lock" ] || { echo "lock file not found: $lock" >&2; exit 1; }

# --- platform key -----------------------------------------------------------
uname_s="$(uname -s)"
uname_m="$(uname -m)"
case "$uname_m" in
  x86_64|amd64) arch="x64" ;;
  aarch64|arm64) arch="arm64" ;;
  *) echo "unsupported architecture: $uname_m" >&2; exit 1 ;;
esac
case "$uname_s" in
  Darwin) key="mac-$arch" ;;
  Linux)
    # musl (alpine) needs the dedicated build
    if [ -f /etc/alpine-release ] || (command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl); then
      key="linux-alpine-$arch"
    else
      key="linux-$arch"
    fi
    ;;
  *) echo "unsupported OS: $uname_s" >&2; exit 1 ;;
esac

# --- read lock (python3 preferred, python fallback) --------------------------
py=""
for c in python3 python; do command -v "$c" >/dev/null 2>&1 && { py="$c"; break; }; done
[ -n "$py" ] || { echo "python3 is required to parse the lock file" >&2; exit 1; }

read -r version asset expected url <<EOF
$("$py" - "$lock" "$key" <<'PYEOF'
import json, sys
lock_path, key = sys.argv[1], sys.argv[2]
with open(lock_path, encoding="utf-8") as fh:
    lock = json.load(fh)
entry = lock["assets"].get(key)
if not entry:
    sys.exit("no asset for platform '%s' in lock file" % key)
url = lock["release_url_template"].format(version=lock["version"], asset=entry["asset"])
print(lock["version"], entry["asset"], entry["sha256"].lower(), url)
PYEOF
)
EOF

bin_dir="$root/bin"
target="$bin_dir/officecli"

sha_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# --- already installed? -----------------------------------------------------
if [ -f "$target" ] && [ "${FORCE:-0}" != "1" ]; then
  if [ "$(sha_of "$target")" = "$expected" ]; then
    echo "OfficeCLI already installed and verified ($version, reported: $("$target" --version 2>/dev/null || echo '?'))"
    exit 0
  fi
  echo "existing binary hash mismatch, reinstalling..."
fi

# --- download ---------------------------------------------------------------
mkdir -p "$bin_dir"
tmp="$bin_dir/.$asset.part"
echo "downloading $asset ($version) ..."
if command -v curl >/dev/null 2>&1; then
  curl -sSL --fail -o "$tmp" "$url"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$tmp" "$url"
else
  echo "curl or wget is required" >&2; exit 1
fi

# --- verify -----------------------------------------------------------------
actual="$(sha_of "$tmp")"
if [ "$actual" != "$expected" ]; then
  rm -f "$tmp"
  echo "SHA-256 mismatch for $asset" >&2
  echo "  expected: $expected" >&2
  echo "  actual:   $actual" >&2
  exit 1
fi

mv -f "$tmp" "$target"
chmod +x "$target"
echo "OK  OfficeCLI $version installed -> $target (reported: $("$target" --version 2>/dev/null || echo '?'))"
echo "    SHA-256 verified: $expected"

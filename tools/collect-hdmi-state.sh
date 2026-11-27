#!/bin/bash
# Run on macOS only, after experimental integration. No system changes.
set -eu
umask 077
out=${1:?Usage: bash collect-hdmi-state.sh OUTPUT_DIRECTORY PHASE}
phase=${2:?Use disconnected, connected, or post-wake}
case "$phase" in disconnected|connected|post-wake) ;; *) echo 'Invalid phase' >&2; exit 2;; esac
mkdir -p "$out"
dir="$out/$phase-$(date +%Y%m%d-%H%M%S)"
mkdir "$dir"
failed=0
capture() {
  local name=$1; shift
  if "$@" > "$dir/$name.txt" 2> "$dir/$name.stderr"; then
    printf '%s PASS\n' "$name" >> "$dir/status.txt"
  else
    printf '%s FAILED\n' "$name" >> "$dir/status.txt"
    failed=1
  fi
}
capture registry ioreg -lw0
capture devices system_profiler SPAudioDataType SPDisplaysDataType
capture kexts kmutil showloaded
capture power pmset -g log
capture version sw_vers
printf '%s\n' 'Review logs for private data before sharing. PASS means collection succeeded, not hardware functionality.'
exit "$failed"

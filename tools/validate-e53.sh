#!/bin/bash
# E5.3 physical validation collector; no system configuration changes.
set -eu
umask 077
[ "$(uname -s)" = Darwin ] || { echo 'macOS required' >&2; exit 2; }
out=${1:?Usage: bash tools/validate-e53.sh OUTPUT_DIRECTORY PHASE METAL_PROBE}
phase=${2:?Specify baseline, connected, reconnected, or post-wake}
probe=${3:?Specify compiled metal_probe executable}
case "$phase" in baseline|connected|reconnected|post-wake) ;; *) exit 2;; esac
[ -x "$probe" ] || { echo 'Metal probe executable required' >&2; exit 2; }
mkdir -p "$out"
dir=$(mktemp -d "$out/$phase.XXXXXXXX")
failed=0
capture() {
    local name=$1 rc=0; shift
    "$@" > "$dir/$name.txt" 2> "$dir/$name.stderr" || rc=$?
    printf '%s\t%s\n' "$name" "$rc" >> "$dir/status.tsv"
    if [ "$rc" -ne 0 ]; then failed=1; fi
}
capture version sw_vers
capture displays system_profiler SPDisplaysDataType
capture audio system_profiler SPAudioDataType
capture loaded kmutil showloaded
capture registry ioreg -lw0
capture power pmset -g log
metal_args=(--iterations 10 --suite advanced)
if [ -n "${4:-}" ]; then metal_args+=(--registry-id "$4"); fi
capture metal "$probe" "${metal_args[@]}"
printf '%s\n' 'Record physical observations separately. Exit zero does not prove HDMI audio or sleep recovery.'
printf '%s\n' 'Review private data before sharing:' "$dir"
exit "$failed"

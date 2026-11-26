#!/usr/bin/env python3
"""Offline, single-connector HDMI/DP lifecycle replay; no driver hooks."""
import argparse
import json
import sys

from hdmi_audio_probe import eld_audio

MAX_INPUT = 1024 * 1024
MAX_EVENTS = 1024
MAX_ELD = 4096


class ReplayError(ValueError):
    pass


def replay(events):
    """Return per-event decisions and current evidence, never hardware readiness.

    Epochs identify a modeled connection lifecycle, not actual IOKit objects.
    Every accepted lifecycle event revokes the previous ELD. Asynchronous
    samples carry the epoch at acquisition, not at completion.
    """
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ReplayError("invalid event list")
    epoch = 0
    state = "disconnected"
    evidence = None
    history = []

    for index, event in enumerate(events):
        if not isinstance(event, dict) or type(event.get("event")) is not str:
            raise ReplayError("invalid event")
        kind = event["event"]
        if kind in ("connect", "disconnect", "suspend", "resume"):
            if set(event) != {"event"}:
                raise ReplayError("unexpected lifecycle fields")
            if kind == "resume":
                if state != "suspended":
                    raise ReplayError("resume without suspend")
                state = "disconnected"
            elif kind == "suspend":
                state = "suspended"
            elif kind == "connect":
                if state == "suspended":
                    raise ReplayError("connect during suspend")
                state = "connected"
            elif state != "suspended":
                state = "disconnected"
            epoch += 1
            evidence = None
            decision = "revoked"
        elif kind == "eld":
            if set(event) != {"event", "epoch", "hex"}:
                raise ReplayError("unexpected ELD fields")
            supplied = event["epoch"]
            raw = event["hex"]
            if (type(supplied) is not int or not 0 <= supplied <= epoch
                    or not isinstance(raw, str) or len(raw) > MAX_ELD * 2
                    or len(raw) % 2 or any(c not in "0123456789abcdefABCDEF" for c in raw)):
                raise ReplayError("invalid sample envelope")
            if supplied != epoch:
                decision = "stale"
            elif state != "connected":
                decision = "inactive"
            else:
                parsed = eld_audio(bytes.fromhex(raw))
                if parsed["status"] == "valid":
                    evidence = parsed
                    decision = "observed"
                else:
                    evidence = None
                    decision = "invalidated"
        else:
            raise ReplayError("unknown event")

        history.append({"index": index, "epoch": epoch, "state": state,
                        "decision": decision,
                        "stereo_pcm16_rates_hz": (
                            evidence["stereo_pcm16_rates_hz"] if evidence else None)})

    return {"schema": 1, "epoch": epoch, "state": state,
            "eld_evidence": evidence, "history": history,
            "limitations": "Synthetic single-connector replay; no live ELD, hardware route, or playback validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", help="JSON array of offline lifecycle events")
    args = parser.parse_args()
    try:
        with open(args.events, "rb") as f:
            raw = f.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ReplayError("input exceeds size limit")
        report = replay(json.loads(raw))
    except (OSError, ValueError, RecursionError):
        # Do not emit arbitrary input or filenames in the report.
        parser.exit(2, "Invalid or unreadable replay input.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

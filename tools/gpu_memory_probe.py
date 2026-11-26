#!/usr/bin/env python3
"""Offline memory-accounting audit with explicit allocation and ownership evidence.

This schema is a diagnostic interchange format, not a native Apple ABI.
No allocation, task, queue or context identity is discovered by this tool.
"""
import argparse
import json
import re
import sys

MAX_INPUT = 4 * 1024 * 1024
MAX_RECORDS = 8192
MAX_LINKS = 32768
U64_MAX = (1 << 64) - 1
SCHEMA = "wex-memory-accounting-v1"


def uint(value, positive=False):
    return type(value) is int and int(positive) <= value < U64_MAX


def records(items, keys, identity):
    if not isinstance(items, list) or len(items) > MAX_RECORDS:
        raise ValueError("invalid record list")
    result = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != keys:
            raise ValueError("invalid record shape")
        key = item[identity]
        if not uint(key, positive=True) or key in result:
            raise ValueError("invalid or duplicate record identity")
        result[key] = item
    return result


def analyze(snapshot):
    if (not isinstance(snapshot, dict) or
            set(snapshot) != {"schema", "clients", "contexts", "queues", "allocations"} or
            snapshot["schema"] != SCHEMA):
        raise ValueError("unsupported memory snapshot")
    clients = records(snapshot["clients"], {"id"}, "id")
    contexts = records(snapshot["contexts"], {"id", "client"}, "id")
    queues = records(snapshot["queues"], {"id", "context", "client"}, "id")
    allocations = records(snapshot["allocations"], {"id", "bytes", "queues"}, "id")

    good_contexts = {}
    for cid, c in contexts.items():
        owner = c["client"]
        if uint(owner, positive=True) and owner in clients:
            good_contexts[cid] = owner
    good_queues = {}
    for qid, q in queues.items():
        owner, ctx = q["client"], q["context"]
        if (uint(owner, positive=True) and uint(ctx, positive=True) and
                good_contexts.get(ctx) == owner):
            good_queues[qid] = owner

    # Count each allocation once, independent of the number of queue references.
    # A bad or unresolved link makes the whole allocation unattributed.
    # Do not assign shared allocation bytes to each owner as exclusive memory.
    exclusive = {client: 0 for client in clients}
    shared_bytes = unattributed_bytes = total_bytes = 0
    exclusive_count = shared_count = unattributed_count = invalid_sizes = links = 0
    for allocation in allocations.values():
        size = allocation["bytes"]
        qids = allocation["queues"]
        if not isinstance(qids, list) or any(not uint(q, positive=True) for q in qids):
            raise ValueError("invalid allocation link")
        links += len(qids)
        if links > MAX_LINKS:
            raise ValueError("too many allocation links")
        if len(qids) != len(set(qids)):
            raise ValueError("duplicate allocation link")
        if not uint(size, positive=True):
            invalid_sizes += 1
            continue
        if total_bytes > U64_MAX - 1 - size:
            raise ValueError("aggregate byte count exceeds range")
        total_bytes += size
        if not qids or any(q not in good_queues for q in qids):
            unattributed_bytes += size
            unattributed_count += 1
            continue
        owners = {good_queues[q] for q in qids}
        if len(owners) == 1:
            exclusive[next(iter(owners))] += size
            exclusive_count += 1
        else:
            shared_bytes += size
            shared_count += 1

    # Export ordinal clients in the input order, never original identifiers.
    return {
        "schema": 1,
        "clients": [{"ordinal": i + 1, "exclusive_observed_bytes": exclusive[cid]}
                    for i, cid in enumerate(clients)],
        "contexts": {"observed": len(contexts), "resolved": len(good_contexts)},
        "queues": {"observed": len(queues), "resolved": len(good_queues)},
        "allocations": {"observed": len(allocations), "invalid_size": invalid_sizes,
                        "exclusive": exclusive_count, "shared": shared_count,
                        "unattributed": unattributed_count},
        "bytes": {"valid_observed_total": total_bytes,
                  "exclusive": sum(exclusive.values()), "shared": shared_bytes,
                  "unattributed": unattributed_bytes},
        "limitations": [
            "Caller-supplied identities, ownership links and byte sizes are unverified.",
            "Use a single coherent snapshot; IDs are local and must not be correlated across captures.",
            "Observed exclusive means one resolved owner among supplied links, not proof of sole physical ownership.",
            "Allocation bytes are not necessarily resident, unique physical pages, GART usage or total per-process VRAM.",
            "Invalid-sized records are excluded from byte sums and counted separately. Missing records are not inferred.",
            "No live queue inspection, kernel pointer reads, allocation or eviction changes."
        ]
    }


# Text snapshots are diagnostic evidence only. Repeated registry properties can
# be aliases of the same accelerator; never add their values together.
COUNTER_KEYS = ("inUseSysMemoryBytes", "inUseVidMemoryBytes",
                "orphanedReusableSysMemoryBytes", "orphanedNonReusableSysMemoryBytes")
COUNTER_PATTERN = re.compile(
    r'"(' + "|".join(COUNTER_KEYS) + r')"\s*=\s*([^\s,}]+)'
)


def analyze_registry_text(snapshot):
    if not isinstance(snapshot, str) or len(snapshot) > MAX_INPUT:
        raise ValueError("invalid registry text")
    observations = {key: {} for key in COUNTER_KEYS}
    invalid = dict.fromkeys(COUNTER_KEYS, 0)
    for match in COUNTER_PATTERN.finditer(snapshot):
        key, token = match.groups()
        if not re.fullmatch(r"[0-9]{1,20}", token):
            invalid[key] += 1
            continue
        value = int(token)
        if value > U64_MAX:
            invalid[key] += 1
            continue
        counts = observations[key]
        counts[value] = counts.get(value, 0) + 1

    counters = {}
    for key, counts in observations.items():
        samples = []
        for value, occurrences in sorted(counts.items()):
            record = {"raw_decimal": str(value), "occurrences": occurrences}
            if value == U64_MAX:
                record["status"] = "all-ones-ambiguous"
            elif value >= 1 << 63:
                record["status"] = "high-bit-set"
                record["signed_int64_candidate"] = str(value - (1 << 64))
            else:
                record["status"] = "unsigned-observed"
            samples.append(record)
        counters[key] = {"distinct_values": samples, "invalid_tokens": invalid[key]}
    return {"schema": "wex-memory-registry-text-v1", "counters": counters,
            "limitations": [
                "Text matches do not establish accelerator identity or coherent capture.",
                "Repeated values are occurrences, not separate allocations; never sum them.",
                "High bit or all-ones is suspicious, not proof of arithmetic underflow.",
                "Signed candidate is an interpretation only, not a corrected byte count.",
                "Missing fields are not zero; no driver or accounting state is changed."
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="offline normalized allocation/ownership JSON or registry text")
    parser.add_argument("--registry-text", action="store_true",
                        help="inspect raw byte-counter observations without attribution")
    args = parser.parse_args()
    try:
        with open(args.snapshot, "rb") as f:
            data = f.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError("input exceeds limit")
        report = (analyze_registry_text(data.decode('utf-8')) if args.registry_text
                  else analyze(json.loads(data)))
    except (OSError, ValueError, RecursionError):
        parser.exit(2, "Invalid or unsupported memory snapshot.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

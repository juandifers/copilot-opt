#!/usr/bin/env python3
"""Fetch six Solomon-100 VRPTW instances into ``data/vrptw_instances/``.

Used only by the exploratory VRPTW Phase 1 stability probe
(``scripts/run_vrptw_probe.py``). Not part of the preregistered CVRP
Stage A pipeline.

Source layout note
------------------
The prompt's preferred source was ``.../VRPTW/Solomon/*.txt`` on the
PyVRP Instances GitHub mirror. That URL returns 404 (the mirror does
not host the original Solomon ``.txt`` distribution); the mirror does
host the equivalent files as ``.../VRPTW/Solomon/*.vrp`` in the
CVRPLIB-extended VRPTW format (``TYPE : CVRPTW``). Those parse cleanly
via ``vrplib.read_instance(..., instance_format='vrplib')`` and carry
the same fields (coords, demand, time_window, service_time, capacity,
vehicles), so we use the ``.vrp`` files as the canonical fetch target.

Usage
-----
::

    python scripts/download_vrptw_instances.py
    python scripts/download_vrptw_instances.py --out-dir data/vrptw_instances
    python scripts/download_vrptw_instances.py --force
    python scripts/download_vrptw_instances.py --instances C101 C102 R101
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

#: Phase 1 probe instances.
DEFAULT_INSTANCES: tuple[str, ...] = (
    "C101", "C201", "R101", "R201", "RC101", "RC201",
)

#: Stable PyVRP-hosted Solomon mirror (CVRPLIB-extended ``.vrp`` format).
DEFAULT_BASE_URL: str = (
    "https://raw.githubusercontent.com/PyVRP/Instances/main/VRPTW/Solomon"
)

#: File extension on the mirror.
INSTANCE_EXT: str = ".vrp"

REQUEST_TIMEOUT_S: float = 30.0


def _instance_url(name: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/{name}{INSTANCE_EXT}"


def download_one(
    name: str, dest_dir: Path, base_url: str, *, force: bool
) -> str:
    """Download a single instance. Returns one of ``"fetched"``, ``"skipped"``.

    Raises on transport error or unexpectedly-empty body so the caller
    surfaces the failure rather than silently writing junk.
    """
    target = dest_dir / f"{name}{INSTANCE_EXT}"
    if target.exists() and target.stat().st_size > 0 and not force:
        return "skipped"

    url = _instance_url(name, base_url)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_S) as resp:
        body = resp.read()
    if not body or b"NODE_COORD_SECTION" not in body:
        raise RuntimeError(
            f"unexpected response for {name}: {len(body)} bytes; "
            f"missing NODE_COORD_SECTION (URL={url})"
        )
    tmp.write_bytes(body)
    os.replace(tmp, target)
    return "fetched"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="download_vrptw_instances",
        description="Fetch Solomon-100 VRPTW instances for the Phase 1 probe.",
    )
    p.add_argument("--out-dir", type=Path, default=Path("data/vrptw_instances"))
    p.add_argument("--base-url", default=os.environ.get(
        "VRPTW_BASE_URL", DEFAULT_BASE_URL))
    p.add_argument("--force", action="store_true",
                   help="Re-download even if file exists.")
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--sleep-between-s", type=float, default=0.1)
    p.add_argument(
        "--instances", nargs="+", default=None,
        metavar="ID",
        help=(
            "Instance IDs to fetch (e.g. C101 C102 R101). "
            "Defaults to the Phase 1 set: "
            + " ".join(DEFAULT_INSTANCES)
        ),
    )
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    instances: tuple[str, ...] = (
        tuple(args.instances) if args.instances else DEFAULT_INSTANCES
    )

    n_fetched = 0
    n_skipped = 0
    failures: list[tuple[str, str]] = []
    for i, name in enumerate(instances, start=1):
        for attempt in range(1, args.retries + 1):
            try:
                status = download_one(
                    name, args.out_dir, args.base_url, force=args.force,
                )
                if status == "fetched":
                    n_fetched += 1
                    print(f"[{i}/{len(instances)}] fetched  {name}{INSTANCE_EXT}")
                else:
                    n_skipped += 1
                    print(f"[{i}/{len(instances)}] skipped  {name}{INSTANCE_EXT} (exists)")
                break
            except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
                if attempt == args.retries:
                    failures.append((name, str(e)))
                    print(f"[{i}/{len(instances)}] FAILED   {name}{INSTANCE_EXT}: {e}",
                          file=sys.stderr)
                else:
                    time.sleep(2 ** attempt)
        if args.sleep_between_s:
            time.sleep(args.sleep_between_s)

    print(f"\nFetched {n_fetched}, skipped {n_skipped}, failed {len(failures)}.")
    if failures:
        print("Failed instances:", file=sys.stderr)
        for name, err in failures:
            print(f"  {name}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

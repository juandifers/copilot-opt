#!/usr/bin/env python3
"""Fetch the 100 Uchoa-X CVRPLIB instances into ``data/instances/``.

This is a one-time setup step. Idempotent — files that already exist on disk
are skipped, so re-running is safe and fast.

Usage::

    python scripts/download_instances.py
    python scripts/download_instances.py --dest data/instances --base-url <mirror>

If the default CVRPLIB URL is unreachable, override it with ``--base-url`` or
the ``CVRPLIB_BASE_URL`` environment variable. The instance list is fixed
(the canonical Uchoa et al. 2017 X-set) and printed under ``--list``.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

#: The 100 Uchoa-X CVRPLIB instances (canonical X-set, Uchoa et al. 2017).
#: Filename pattern: ``X-n{N}-k{K}`` where N = depot + customers, K is the
#: instance's suggested vehicle count.
ALL_X_INSTANCES: tuple[str, ...] = (
    "X-n101-k25", "X-n106-k14", "X-n110-k13", "X-n115-k10", "X-n120-k6",
    "X-n125-k30", "X-n129-k18", "X-n134-k13", "X-n139-k10", "X-n143-k7",
    "X-n148-k46", "X-n153-k22", "X-n157-k13", "X-n162-k11", "X-n167-k10",
    "X-n172-k51", "X-n176-k26", "X-n181-k23", "X-n186-k15", "X-n190-k8",
    "X-n195-k51", "X-n200-k36", "X-n204-k19", "X-n209-k16", "X-n214-k11",
    "X-n219-k73", "X-n223-k34", "X-n228-k23", "X-n233-k16", "X-n237-k14",
    "X-n242-k48", "X-n247-k50", "X-n251-k28", "X-n256-k16", "X-n261-k13",
    "X-n266-k58", "X-n270-k35", "X-n275-k28", "X-n280-k17", "X-n284-k15",
    "X-n289-k60", "X-n294-k50", "X-n298-k31", "X-n303-k21", "X-n308-k13",
    "X-n313-k71", "X-n317-k53", "X-n322-k28", "X-n327-k20", "X-n331-k15",
    "X-n336-k84", "X-n344-k43", "X-n351-k40", "X-n359-k29", "X-n367-k17",
    "X-n376-k94", "X-n384-k52", "X-n393-k38", "X-n401-k29", "X-n411-k19",
    "X-n420-k130", "X-n429-k61", "X-n439-k37", "X-n449-k29", "X-n459-k26",
    "X-n469-k138", "X-n480-k70", "X-n491-k59", "X-n502-k39", "X-n513-k21",
    "X-n524-k153", "X-n536-k96", "X-n548-k50", "X-n561-k42", "X-n573-k30",
    "X-n586-k159", "X-n599-k92", "X-n613-k62", "X-n627-k43", "X-n641-k35",
    "X-n655-k131", "X-n670-k130", "X-n685-k75", "X-n701-k44", "X-n716-k35",
    "X-n733-k159", "X-n749-k98", "X-n766-k71", "X-n783-k48", "X-n801-k40",
    "X-n819-k171", "X-n837-k142", "X-n856-k95", "X-n876-k59", "X-n895-k37",
    "X-n916-k207", "X-n936-k151", "X-n957-k87", "X-n979-k58", "X-n1001-k43",
)
assert len(ALL_X_INSTANCES) == 100, "Uchoa X-set must have exactly 100 instances"

#: Default base URL for the X-set ``.vrp`` files. Points at the PyVRP project's
#: instance mirror on GitHub, which hosts the canonical Uchoa-X files under
#: stable URLs. The original CVRPLIB host (``vrp.atd-lab.inf.puc-rio.br``) was
#: re-architected in 2024 to use numeric instance IDs; direct ``.vrp`` filenames
#: no longer resolve there. Override via ``--base-url`` or ``CVRPLIB_BASE_URL``
#: if you have a preferred mirror.
DEFAULT_BASE_URL: str = "https://raw.githubusercontent.com/PyVRP/Instances/main/CVRP"

#: Per-request timeout in seconds.
REQUEST_TIMEOUT_S: float = 30.0


def _instance_url(name: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/{name}.vrp"


def download_instance(name: str, dest_dir: Path, base_url: str, *, force: bool = False) -> bool:
    """Download a single instance. Returns True if a fetch happened, False if skipped."""
    target = dest_dir / f"{name}.vrp"
    if target.exists() and not force:
        return False
    url = _instance_url(name, base_url)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_S) as resp:
        body = resp.read()
    if not body or b"DIMENSION" not in body:
        raise RuntimeError(f"unexpected response for {name}: {len(body)} bytes, no DIMENSION field")
    tmp.write_bytes(body)
    tmp.replace(target)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="download_instances", description=__doc__)
    p.add_argument("--dest", type=Path, default=Path("data/instances"))
    p.add_argument("--base-url", default=os.environ.get("CVRPLIB_BASE_URL", DEFAULT_BASE_URL))
    p.add_argument("--force", action="store_true", help="Re-download even if file exists.")
    p.add_argument("--list", action="store_true", help="Print the 100 instance names and exit.")
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--sleep-between-s", type=float, default=0.1)
    args = p.parse_args(argv)

    if args.list:
        for name in ALL_X_INSTANCES:
            print(name)
        return 0

    args.dest.mkdir(parents=True, exist_ok=True)
    n_fetched = 0
    n_skipped = 0
    failures: list[tuple[str, str]] = []
    for i, name in enumerate(ALL_X_INSTANCES, start=1):
        for attempt in range(1, args.retries + 1):
            try:
                fetched = download_instance(name, args.dest, args.base_url, force=args.force)
                if fetched:
                    n_fetched += 1
                    print(f"[{i:3d}/100] fetched  {name}")
                else:
                    n_skipped += 1
                break
            except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
                if attempt == args.retries:
                    failures.append((name, str(e)))
                    print(f"[{i:3d}/100] FAILED   {name}: {e}", file=sys.stderr)
                else:
                    time.sleep(2 ** attempt)
        if args.sleep_between_s:
            time.sleep(args.sleep_between_s)

    print(f"\nFetched {n_fetched}, skipped {n_skipped}, failed {len(failures)}.")
    if failures:
        print("Failed instances (re-run to retry):", file=sys.stderr)
        for name, err in failures:
            print(f"  {name}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Controlled acquisition of pilot instances.

Policy (see project prompt):
- Manual-first ingestion: if data/raw/cvrplib/ already has .vrp files, do nothing.
- Never auto-download all of CVRPLIB.
- Fallback subset is limited to Uchoa X, n in [100, 250], <= 20 instances,
  stratified by size with diversity in vehicle count k.

The CVRPLIB endpoint is opaque-numeric:
    https://galgos.inf.puc-rio.br/cvrplib/index.php/en/download/instance/{id}
    https://galgos.inf.puc-rio.br/cvrplib/index.php/en/download/instanceSolution/{id}
"""
from __future__ import annotations

import logging
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CVRPLIB_INSTANCE_URL = (
    "https://galgos.inf.puc-rio.br/cvrplib/index.php/en/download/instance/{id}"
)
CVRPLIB_SOLUTION_URL = (
    "https://galgos.inf.puc-rio.br/cvrplib/index.php/en/download/instanceSolution/{id}"
)


@dataclass(frozen=True)
class PilotInstance:
    name: str
    cvrplib_id: int
    n: int
    k: int
    bin_label: str


# Pilot subset chosen for stratified n and diverse k.
# Ids verified against the live CVRPLIB endpoint on 2026-04-24.
PILOT_SUBSET: tuple[PilotInstance, ...] = (
    # Small: n in [100, 150]
    PilotInstance("X-n101-k25", 158, 101, 25, "small"),
    PilotInstance("X-n110-k13", 160, 110, 13, "small"),
    PilotInstance("X-n120-k6",  162, 120, 6,  "small"),
    PilotInstance("X-n134-k13", 165, 134, 13, "small"),
    PilotInstance("X-n148-k46", 168, 148, 46, "small"),
    # Medium: n in (150, 200]
    PilotInstance("X-n153-k22", 169, 153, 22, "medium"),
    PilotInstance("X-n162-k11", 171, 162, 11, "medium"),
    PilotInstance("X-n172-k51", 173, 172, 51, "medium"),
    PilotInstance("X-n181-k23", 175, 181, 23, "medium"),
    PilotInstance("X-n190-k8",  177, 190, 8,  "medium"),
    # Large: n in (200, 250]
    PilotInstance("X-n200-k36", 179, 200, 36, "large"),
    PilotInstance("X-n214-k11", 182, 214, 11, "large"),
    PilotInstance("X-n219-k73", 183, 219, 73, "large"),
    PilotInstance("X-n228-k23", 185, 228, 23, "large"),
    PilotInstance("X-n247-k50", 189, 247, 50, "large"),
)


def _http_get(url: str, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vrpbench/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def already_has_vrp(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.glob("*.vrp"))


def acquire_pilot(
    raw_dir: Path,
    *,
    enable_fallback: bool = True,
    subset: tuple[PilotInstance, ...] = PILOT_SUBSET,
) -> list[dict]:
    """Ensure raw_dir contains pilot .vrp files; fetch fallback subset if empty.

    Returns a list of per-instance provenance dicts recording how each file
    arrived (manual vs downloaded).
    """
    raw_dir.mkdir(parents=True, exist_ok=True)

    existing = already_has_vrp(raw_dir)
    provenance: list[dict] = []

    if existing:
        logger.info("Found %d existing .vrp files; skipping download.", len(existing))
        for p in existing:
            provenance.append({
                "name": p.stem,
                "path": str(p),
                "source": "manual",
                "url": None,
            })
        return provenance

    if not enable_fallback:
        logger.warning("No .vrp files present and fallback is disabled.")
        return provenance

    logger.info("No .vrp files present; downloading Uchoa X pilot subset (%d instances).", len(subset))
    for inst in subset:
        vrp_url = CVRPLIB_INSTANCE_URL.format(id=inst.cvrplib_id)
        sol_url = CVRPLIB_SOLUTION_URL.format(id=inst.cvrplib_id)
        vrp_path = raw_dir / f"{inst.name}.vrp"
        sol_path = raw_dir / f"{inst.name}.sol"

        try:
            vrp_bytes = _http_get(vrp_url)
            vrp_path.write_bytes(vrp_bytes)
        except urllib.error.URLError as e:
            logger.error("Failed to download %s from %s: %s", inst.name, vrp_url, e)
            provenance.append({
                "name": inst.name,
                "path": None,
                "source": "download_failed",
                "url": vrp_url,
                "error": str(e),
            })
            continue

        # Best-effort BKS .sol; absence is not fatal.
        sol_ok = False
        try:
            sol_bytes = _http_get(sol_url)
            if sol_bytes and not sol_bytes.lstrip().startswith(b"<"):
                sol_path.write_bytes(sol_bytes)
                sol_ok = True
        except urllib.error.URLError as e:
            logger.warning("No .sol for %s: %s", inst.name, e)

        provenance.append({
            "name": inst.name,
            "path": str(vrp_path),
            "source": "downloaded",
            "url": vrp_url,
            "bks_source": "downloaded" if sol_ok else "unavailable",
        })
    return provenance

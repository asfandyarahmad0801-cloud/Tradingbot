"""Append-only research registry.

Every evaluation -- accepted, rejected, or inconclusive -- is appended as one
JSON line. Nothing is ever deleted or rewritten: a hypothesis that failed is
evidence too, and the count of everything tried is what multiple-testing
corrections need.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.call(["git", "diff", "--quiet"], stderr=subprocess.DEVNULL) != 0
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def dataset_fingerprint(manifest_path: Path | str, symbols: list[str]) -> str:
    """Hash of the sorted source-file checksums for the given symbols: two runs
    with the same fingerprint used byte-identical inputs."""
    lines = []
    p = Path(manifest_path)
    if p.exists():
        for ln in p.read_text().splitlines():
            rec = json.loads(ln)
            if any(f"/{s}/" in rec["path"] or rec["path"].startswith(f"{s}/") for s in symbols):
                lines.append(f"{rec['path']}:{rec['sha256']}")
    return hashlib.sha256("\n".join(sorted(set(lines))).encode()).hexdigest()[:16]


class Registry:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> dict:
        rec = {"recorded_at": datetime.now(timezone.utc).isoformat(), **record}
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, default=_json_default, allow_nan=True) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(ln) for ln in self.path.read_text().splitlines() if ln.strip()]


def _json_default(o):
    import numpy as np
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))

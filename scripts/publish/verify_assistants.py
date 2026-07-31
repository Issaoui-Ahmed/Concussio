"""Read the instructions back off the remote assistants and confirm the local corpus landed.

`update_fuelix_instructions.py` reports what it *sent*. This reports what the remote actually
*has* — the difference matters, because a partially applied patch would otherwise look like a
successful run.

    python -m scripts.publish.verify_assistants

Exits non-zero if any assistant is missing, unreachable, or not carrying the local corpus.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

import requests
from dotenv import load_dotenv

from core.fuelix_chat import ASSISTANT_ENV_BY_USER_TYPE
from scripts.content_pipeline.corpus import CORPUS_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Sampled from the head, middle and tail of the corpus. Checking one marker would pass on a
# truncated upload; spreading them proves the whole document is present.
SAMPLE_COUNT = 3
SAMPLE_LENGTH = 60


def _base_url() -> str:
    return (os.getenv("FUELIX_API_BASE_URL") or "https://api.fuelix.ai/v1").rstrip("/")


def _headers() -> Dict[str, str]:
    key = (os.getenv("FUELIX_API_KEY") or os.getenv("FUEL_IX_API_KEY") or "").strip()
    if not key:
        sys.exit("FUELIX_API_KEY is not set — cannot verify.")
    headers = {"Authorization": f"Bearer {key}"}
    product_id = os.getenv("FUELIX_PRODUCT_ID", "core").strip()
    if product_id:
        headers["product-id"] = product_id
    return headers


def _markers(corpus: str) -> List[str]:
    """Distinctive slices from across the corpus."""
    usable = [line.strip() for line in corpus.splitlines() if len(line.strip()) > SAMPLE_LENGTH]
    if not usable:
        sys.exit("Corpus has no lines long enough to sample — refusing to verify.")
    step = max(1, len(usable) // (SAMPLE_COUNT + 1))
    return [usable[step * (i + 1)][:SAMPLE_LENGTH] for i in range(SAMPLE_COUNT)]


def main() -> int:
    corpus = CORPUS_PATH.read_text(encoding="utf-8")
    markers = _markers(corpus)

    resolved = {
        role: os.getenv(env_var, "").strip()
        for role, env_var in ASSISTANT_ENV_BY_USER_TYPE.items()
    }
    configured = {role: value for role, value in resolved.items() if value}

    if not configured:
        sys.exit(
            "No FUELIX_ASSISTANT_ID_* variables are set — cannot verify. "
            "Refusing to report success."
        )
    missing_env = sorted(set(resolved) - set(configured))
    if missing_env:
        print(f"WARNING: no assistant id configured for: {missing_env}")

    print(f"Verifying {len(configured)} assistant(s) against {CORPUS_PATH.name}\n")
    failures = 0

    for role, assistant_id in sorted(configured.items()):
        try:
            response = requests.get(
                f"{_base_url()}/assistants/{assistant_id}", headers=_headers(), timeout=60
            )
        except Exception as exc:
            print(f"  FAIL {role}: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        if response.status_code != 200:
            print(f"  FAIL {role}: HTTP {response.status_code}")
            failures += 1
            continue

        instructions = (response.json() or {}).get("instructions") or ""
        found = [marker for marker in markers if marker in instructions]
        ok = len(found) == len(markers)
        if not ok:
            failures += 1
        print(
            f"  {'OK  ' if ok else 'FAIL'} {role:<26} {len(instructions):>7} chars  "
            f"markers {len(found)}/{len(markers)}"
        )

    print()
    if failures:
        print(f"{failures} assistant(s) are NOT carrying the current corpus.")
        return 1
    print(f"All {len(configured)} assistants carry the current corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

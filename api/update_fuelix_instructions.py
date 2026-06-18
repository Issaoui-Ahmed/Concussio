"""Patch ONLY the `instructions` field on the existing ConcussCare Fuel IX assistants.

Unlike rebuild_fuelix_assistants.py, this never creates or deletes assistants and never
touches the model, vector-store attachments (tool_resources), or metadata. It simply
re-pushes the latest instructions from core.prompts to each assistant that already exists.
"""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.prompts import build_fuelix_assistant_instructions
from api.rebuild_fuelix_assistants import (
    ASSISTANT_SPECS,
    _find_by_name,
    _load_env,
    _paginated_items,
    _request,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch only the instructions field on existing ConcussCare Fuel IX assistants."
    )
    parser.add_argument("--execute", action="store_true", help="Apply changes. Defaults to dry-run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env()
    dry_run = not args.execute

    print(f"Fuel IX instructions update ({'DRY RUN' if dry_run else 'EXECUTE'})")
    print("Scope: instructions field only. model, vector stores (tool_resources), and metadata are left untouched.")

    existing = _paginated_items("/assistants", params={"order": "desc"})

    changed = 0
    skipped = 0
    failed = 0

    for user_type, name in ASSISTANT_SPECS:
        match = _find_by_name(existing, name)
        if not match:
            print(f"skip (not found): {name}")
            skipped += 1
            continue

        assistant_id = match.get("id")
        new_instructions = build_fuelix_assistant_instructions(user_type)
        current_instructions = match.get("instructions") or ""

        if current_instructions.strip() == new_instructions.strip():
            print(f"unchanged: {name} ({assistant_id})")
            continue

        if dry_run:
            print(f"would patch instructions: {name} ({assistant_id})")
            changed += 1
            continue

        try:
            _request("POST", f"/assistants/{assistant_id}", json_body={"instructions": new_instructions})
            print(f"patched: {name} ({assistant_id})")
            changed += 1
        except Exception as exc:
            print(f"failed: {name} ({assistant_id}) -> {exc}")
            failed += 1

    verb = "would change" if dry_run else "changed"
    print(f"Summary: {changed} {verb}, {skipped} not found, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

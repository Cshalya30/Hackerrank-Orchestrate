"""Eval CLI. Run: python code/evaluation/main.py [--pred PATH] [--gold PATH] [--dump PATH]

Default compares repo-root output.csv against dataset/sample_output.csv.
--dump writes the full per-case miss list (capped output to stdout; full to file).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval import format_report, load, score  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    args = sys.argv[1:]

    def _arg(flag: str, default: str) -> str:
        return args[args.index(flag) + 1] if flag in args else default

    pred_path = Path(_arg("--pred", str(REPO_ROOT / "output.csv")))
    gold_path = Path(_arg("--gold", str(REPO_ROOT / "dataset" / "sample_output.csv")))
    dump_path = Path(_arg("--dump", "")) if "--dump" in args else None

    pred = load(pred_path)
    gold = load(gold_path)
    result = score(pred, gold)

    print(f"pred={pred_path}")
    print(f"gold={gold_path}")
    print(format_report(result))

    if result["misses"]:
        print("\nfirst 10 misses:")
        for m in result["misses"][:10]:
            print(" -", m)

    if dump_path:
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nfull result dumped to {dump_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Evaluation of the extraction on the annotated fictitious documents.

uv run python scripts/evaluate.py            # rules only
uv run python scripts/evaluate.py --llm      # rules + configured Ollama model
"""

import argparse
import sys
import time

from binder.samples import build_samples
from binder.schemas import Extraction
from binder.services import ingest, llm, rules
from binder.services.text import read_document

FIELDS = ["category", "doc_type", "amount", "issue_date", "due_date", "expiry_date", "reference"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    # The Windows console (cp1252) cannot display ✓ and ✗.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.llm and not llm.is_available():
        raise SystemExit("Model unavailable: check `ollama list` and BINDER_LLM_MODEL")

    hits = dict.fromkeys(FIELDS, 0)
    samples = build_samples()
    started = time.perf_counter()
    for sample in samples:
        text = read_document(sample.pdf(), "application/pdf").text
        result: Extraction = rules.extract(text)
        if args.llm:
            result = ingest.merge(result, llm.extract(text))
        errors = []
        for field in FIELDS:
            expected = sample.expected.get(field)
            if getattr(result, field) == expected:
                hits[field] += 1
            else:
                errors.append(f"{field}={getattr(result, field)!r} (expected {expected!r})")
        print(f"{'✓' if not errors else '✗'} {sample.filename:28} {'; '.join(errors)}")

    elapsed = time.perf_counter() - started
    total = len(samples) * len(FIELDS)
    print("\nAccuracy per field:")
    for field in FIELDS:
        print(f"  {field:12} {hits[field] / len(samples):6.1%}")
    print(f"  {'overall':12} {sum(hits.values()) / total:6.1%}")
    print(f"\n{len(samples)} documents in {elapsed:.1f} s")


if __name__ == "__main__":
    main()

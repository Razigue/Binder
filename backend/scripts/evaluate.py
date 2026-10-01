"""Évaluation de l'extraction sur les documents fictifs annotés.

uv run python scripts/evaluate.py            # règles seules
uv run python scripts/evaluate.py --llm      # règles + modèle Ollama configuré
"""

import argparse
import sys
import time

from binder.samples import build_samples
from binder.schemas import Extraction
from binder.services import ingest, llm, rules
from binder.services.text import read_document

FIELDS = ["category", "amount", "issue_date", "due_date", "expiry_date", "reference"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    args = parser.parse_args()
    # La console Windows (cp1252) ne sait pas afficher ✓ et ✗.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.llm and not llm.is_available():
        raise SystemExit("Modèle indisponible : vérifiez `ollama list` et BINDER_LLM_MODEL")

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
                errors.append(f"{field}={getattr(result, field)!r} (attendu {expected!r})")
        print(f"{'✓' if not errors else '✗'} {sample.filename:28} {'; '.join(errors)}")

    elapsed = time.perf_counter() - started
    total = len(samples) * len(FIELDS)
    print("\nPrécision par champ :")
    for field in FIELDS:
        print(f"  {field:12} {hits[field] / len(samples):6.1%}")
    print(f"  {'global':12} {sum(hits.values()) / total:6.1%}")
    print(f"\n{len(samples)} documents en {elapsed:.1f} s")


if __name__ == "__main__":
    main()

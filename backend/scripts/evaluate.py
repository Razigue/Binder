"""Evaluation of the reading: type, category and fields of each document, against what a person
checked. See docs/evaluation.md.

uv run python scripts/evaluate.py                     # demo documents, rules (demo mode)
uv run python scripts/evaluate.py --llm               # demo documents, local model + rules
uv run python scripts/evaluate.py --corpus DIR        # your annotated documents, model + rules
uv run python scripts/evaluate.py --corpus DIR --annotate          # draft the annotations
uv run python scripts/evaluate.py --corpus DIR --report run.json   # keep the results
uv run python scripts/evaluate.py --corpus DIR --model qwen3.5:27b # another local model

Everything stays on the machine: the documents are read here and only shown to the local model.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from binder.config import get_settings
from binder.samples import build_samples
from binder.schemas import Extraction
from binder.services import ingest, llm
from binder.services.text import SUPPORTED_MIME

# Fields scored, in the order they are reported. Annotations may leave some out.
FIELDS = [
    "category", "doc_type", "issuer", "amount", "issue_date", "due_date", "expiry_date",
    "reference", "person",
]  # fmt: skip
# Free-text fields: one spelling inside the other counts ("EDF" for "EDF SA").
LOOSE = {"issuer", "person"}


@dataclass
class Case:
    name: str
    data: bytes
    mime: str
    expected: dict[str, Any]
    annotation: Path | None = None


@dataclass
class Result:
    name: str
    got: dict[str, Any]
    errors: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    seconds: float = 0.0


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def same(name: str, got: Any, expected: Any) -> bool:
    if expected is None or got is None:
        return expected is None and got is None
    if name == "amount":
        return abs(float(got) - float(expected)) < 0.01
    if name.endswith("_date"):
        return str(got)[:10] == str(expected)[:10]
    a, b = _plain(got), _plain(expected)
    if name in LOOSE:
        return bool(a and b) and (a in b or b in a)
    return a == b


def fields_of(ext: Extraction) -> dict[str, Any]:
    data = ext.model_dump(mode="json")
    return {f: data.get(f) for f in FIELDS}


def demo_cases() -> Iterator[Case]:
    for sample in build_samples():
        expected = {k: v.value if hasattr(v, "value") else v for k, v in sample.expected.items()}
        expected = {k: v.isoformat() if isinstance(v, date) else v for k, v in expected.items()}
        yield Case(sample.filename, sample.pdf(), "application/pdf", expected)


MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
}


def corpus_cases(folder: Path) -> Iterator[Case]:
    """Every supported file of the folder (recursively), with `<file>.json` beside it."""
    for path in sorted(folder.rglob("*")):
        mime = MIME_BY_SUFFIX.get(path.suffix.lower())
        if not path.is_file() or mime not in SUPPORTED_MIME:
            continue
        annotation = path.with_name(path.name + ".json")
        expected: dict[str, Any] = {}
        if annotation.exists():
            raw = json.loads(annotation.read_text(encoding="utf-8"))
            expected = {k: v for k, v in raw.items() if k in FIELDS}
        yield Case(
            path.relative_to(folder).as_posix(), path.read_bytes(), mime, expected, annotation
        )


def run(case: Case, use_llm: bool) -> Result:
    started = time.perf_counter()
    _, ext = ingest.extract(case.data, case.mime, use_llm=use_llm)
    result = Result(case.name, fields_of(ext), seconds=time.perf_counter() - started)
    for name, expected in case.expected.items():
        if not same(name, result.got.get(name), expected):
            result.errors[name] = (result.got.get(name), expected)
    return result


def annotate(case: Case, use_llm: bool) -> bool:
    """Writes the current reading beside the file, for a person to check and correct."""
    assert case.annotation is not None
    if case.annotation.exists():
        return False
    _, ext = ingest.extract(case.data, case.mime, use_llm=use_llm)
    draft = {"_check": "Correct every value, then delete this line.", **fields_of(ext)}
    case.annotation.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return True


def report(results: list[Result], cases: list[Case], engine: str) -> dict[str, Any]:
    scored = Counter(f for c in cases for f in c.expected)
    hits = Counter(
        f for c, r in zip(cases, results, strict=True) for f in c.expected if f not in r.errors
    )
    confusions = Counter(
        f"{r.errors['category'][1]} -> {r.errors['category'][0]}"
        for r in results
        if "category" in r.errors
    )
    types = Counter(
        f"{r.errors['doc_type'][1]} -> {r.errors['doc_type'][0]}"
        for r in results
        if "doc_type" in r.errors
    )
    total = sum(scored.values())
    return {
        "engine": engine,
        "documents": len(results),
        "fully_right": sum(not r.errors for r in results),
        "accuracy": {f: round(hits[f] / scored[f], 3) for f in FIELDS if scored[f]},
        "overall": round(sum(hits.values()) / total, 3) if total else None,
        "seconds_per_document": round(sum(r.seconds for r in results) / max(len(results), 1), 2),
        "category_confusions": dict(confusions.most_common(10)),
        "doc_type_confusions": dict(types.most_common(10)),
        "results": [
            {"file": r.name, "got": r.got, "errors": {k: list(v) for k, v in r.errors.items()}}
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--llm", action="store_true", help="demo documents: use the local model")
    parser.add_argument("--corpus", type=Path, help="folder of real documents to evaluate")
    parser.add_argument("--annotate", action="store_true", help="draft the missing .json files")
    parser.add_argument("--report", type=Path, help="write the results as JSON")
    parser.add_argument("--model", help="Ollama model to use instead of the configured one")
    parser.add_argument("--rules", action="store_true", help="corpus: rules only, no model")
    args = parser.parse_args()
    # The Windows console (cp1252) cannot display ✓ and ✗.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.model:
        llm.select(args.model)
    use_llm = (args.llm or args.corpus is not None) and not args.rules
    if use_llm and not (get_settings().llm_enabled and llm.is_available()):
        raise SystemExit(f"Model {llm.model()} unavailable: check `ollama list`")

    if args.corpus is not None:
        if not args.corpus.is_dir():
            raise SystemExit(f"Not a folder: {args.corpus}")
        cases = list(corpus_cases(args.corpus))
        if args.annotate:
            written = sum(annotate(c, use_llm) for c in cases)
            print(f"{written} annotation(s) drafted in {args.corpus}: check each one.")
            return
        unannotated = [c.name for c in cases if not c.expected]
        if unannotated:
            print(f"{len(unannotated)} file(s) without annotation skipped (--annotate drafts them)")
        cases = [c for c in cases if c.expected]
    else:
        cases = list(demo_cases())
    if not cases:
        raise SystemExit("Nothing to evaluate")

    engine = f"{llm.model()} + rules" if use_llm else "rules"
    results = []
    for case in cases:
        result = run(case, use_llm)
        results.append(result)
        errors = "; ".join(f"{k}={g!r} (expected {e!r})" for k, (g, e) in result.errors.items())
        print(f"{'✓' if not result.errors else '✗'} {case.name:32} {errors}")

    summary = report(results, cases, engine)
    print(f"\n{engine}: {summary['fully_right']}/{summary['documents']} documents fully right")
    print("Accuracy per field:")
    for name, value in summary["accuracy"].items():
        print(f"  {name:12} {value:6.1%}")
    if summary["overall"] is not None:
        print(f"  {'overall':12} {summary['overall']:6.1%}")
    for title, key in (("Category", "category_confusions"), ("Type", "doc_type_confusions")):
        if summary[key]:
            print(f"{title} mistakes (expected -> read): ", end="")
            print(", ".join(f"{k} ×{n}" for k, n in summary[key].items()))
    print(f"{summary['seconds_per_document']} s per document")
    if args.report:
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
        print(f"Results written to {args.report}")


if __name__ == "__main__":
    main()

# Evaluation of the reading

`backend/scripts/evaluate.py` measures what Binder reads from a document (category, type, issuer,
amount, dates, reference, person) against what a person checked. It runs the same reading as the
app (`ingest.extract`: text or OCR, page images for scans, local model, rules), without the
corrections learned from the user. Everything stays on the machine: files are read locally and
shown only to the local model.

## Demo documents

```bash
cd backend
uv run python scripts/evaluate.py          # rules (what the demo runs without a model)
uv run python scripts/evaluate.py --llm    # local model + rules (the product)
```

The 21 documents of `binder/samples.py` are fictitious and the rules were tuned on them: their
score checks that the demo works, not that Binder reads real paperwork. Results on 1 October 2026
(RTX 4080 SUPER, `qwen3.5:9b`): rules 100%; model + rules 17/21 documents fully right, 96.9% of
fields, 4 s per document.

## A corpus of real documents

This is the measure that counts. Build it from your own paperwork and keep it **outside the
repository** (it holds personal data):

1. Put the files in a folder (PDF, JPEG, PNG, HEIC, TIFF; subfolders are fine). Aim for about
   100 documents covering the categories, with scans and phone photos, not only clean PDFs.
2. Draft the annotations from Binder's current reading:

   ```bash
   uv run python scripts/evaluate.py --corpus ~/binder-corpus --annotate
   ```

   Each file gets a `<file>.json` beside it (`facture.pdf.json`). Existing ones are never
   overwritten.
3. Check every value by hand against the document, then delete the `_check` line. Leave out a
   field you cannot decide; `null` means the document has none.

   ```json
   {
     "category": "energy",
     "doc_type": "invoice",
     "issuer": "EDF",
     "amount": 94.37,
     "issue_date": "2026-09-18",
     "due_date": "2026-10-12",
     "expiry_date": null,
     "reference": "6012 3456 78",
     "person": "Camille Martin"
   }
   ```

   Values: `category` and `doc_type` are the identifiers of `models.py` (`Category`, `DocType`);
   dates are `YYYY-MM-DD`; amounts are numbers.
4. Run it:

   ```bash
   uv run python scripts/evaluate.py --corpus ~/binder-corpus --report run-qwen9b.json
   uv run python scripts/evaluate.py --corpus ~/binder-corpus --model qwen3.5:27b --report run-27b.json
   uv run python scripts/evaluate.py --corpus ~/binder-corpus --rules   # without a model
   ```

The script prints each document with its mistakes, the accuracy per field, the category and type
confusions, and the time per document. `--report` keeps everything as JSON to compare models or
prompts over time.

## Scoring

- `category`, `doc_type`, `reference`: equal once case, accents, spaces and punctuation are
  ignored.
- `issuer`, `person`: one spelling inside the other counts ("EDF" for "EDF SA").
- `amount`: within one cent. Dates: same day.
- A field missing from the annotation is not scored.

When a mistake comes back on real documents, fix the model path first (prompt, type hints in
`llm.TYPE_HINTS`, merge in `ingest.merge`): the rules only need to run the demo.

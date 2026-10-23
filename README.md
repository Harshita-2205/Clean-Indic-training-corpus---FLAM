# Flam assignment: Hindi and Hinglish corpus pipeline

A small, reproducible data-engineering project for building a cleaned Hindi/Hinglish text corpus, holding out evaluation items, and recording contamination checks. The implementation uses Python's standard library only.

## Reproduce

```bash
./download.sh                 # network required; raw files are preserved verbatim
./run.sh raw out               # offline; writes clean/, ledger.jsonl, eval.jsonl,
                               # contamination.jsonl, and manifest.json
```

`download.sh` downloads a pinned Hindi Wikipedia dump and the PHINC dataset. It writes `raw/sources.json` with URLs, licenses, UTC download time, byte counts, and SHA-256 hashes. Never edit files under `raw/`; rerun the pipeline from those files.

## Output schema

- `clean/documents.jsonl`: `id`, `text`, `lang`, `source`
- `ledger.jsonl`: one record for each valid input row and malformed JSONL/CSV line, with status, stage, reason, and duplicate link
- `eval.jsonl`: deterministic 200-item PHINC holdout
- `contamination.jsonl`: detected training items removed because they match an eval item
- `manifest.json`: source metadata, input hashes, method settings, and observed counts

The run writes to a fresh staging directory and swaps it into place only after completion. A failed run leaves the previous completed output intact; rerunning starts clean, so output rows do not accumulate across attempts.

## Design choices and known limits

- Input is streamed record by record. MediaWiki XML uses `iterparse`; CSV/JSONL are read line by line. The 200-item holdout and disk-backed SQLite dedupe index are bounded independently of corpus size.
- Normalization applies Unicode NFC, removes control/format characters (except whitespace), and collapses whitespace. PII redaction covers email, Aadhaar-like 12-digit strings, PAN, and Indian phone numbers.
- Language labels are inferred from script plus a small transparent Romanized-Hindi vocabulary. This is a heuristic: expand and validate it on a manually labeled sample before production.
- Exact duplicates use normalized redacted text. Near duplicates use 64-bit character 5-gram SimHash (Hamming <= 6) plus character 5-gram Jaccard >= 0.82. The Jaccard gate protects distinct short articles that share a template. The numeric-token guard preserves years and quantities while ignoring digits inside @handles and URLs.
- Evaluation contamination compares each selected training row against all 200 held-out vectors, including Devanagari-to-Latin transliterations. Its separate gate is Hamming <= 16, Jaccard >= 0.70, and equal numeric tokens after ignoring digits in @handles and URLs. The run writes rejected review candidates to `eval_candidate_reviews.jsonl`; approximate transliteration still cannot prove absence of every leak.
- Wikipedia content is CC BY-SA 4.0 and PHINC is listed CC BY 4.0. Preserve attribution and the applicable share-alike terms. The raw corpus is deliberately excluded from the submission sample.

See `DECISIONS.md` for observed counts, reviewed examples, and the engineering discussion. See `docs/project_explanation.pdf` for the detailed walkthrough and follow-up preparation.

# Evaluation

> **Status: not run yet.** No real jobs have been classified. The build environment had no
> network access to the job APIs or the LLM, so there are no accuracy numbers below yet. This
> file gives the method. The results section gets filled from `evaluation/eval_report.md`
> after the steps below are done on real data. No number here may be written by hand.

## Method

1. **Sample.** After the pipeline has classified real jobs:
   ```bash
   python -m evaluation.sample            # 50 jobs, seed "beep-eval-1" -> evaluation/eval_set.csv
   ```
   The sample is a deterministic pseudo-random draw (`ORDER BY md5(seed || id)`) over all
   classified jobs, so anyone with the same database and seed gets the same 50 jobs. It won't
   overwrite an existing CSV, which protects labels already entered.

2. **Verify by hand.** Open `evaluation/eval_set.csv` (Excel or Google Sheets). For each row,
   read the posting (title, location, excerpt, and the original link when the excerpt isn't
   enough) and fill in:
   - `verified_role`: one of the 14 categories, using the definitions in `PROMPTS.md`.
   - `verified_cities`: semicolon-separated cities, `Remote` for remote, `Unknown` if the
     posting names no city.
   - `is_ambiguous`: `yes` if a careful reader could reasonably pick another label.
   - `notes`: why, for anything ambiguous or wrong.

   Label from the posting itself, not from the predicted columns. Covering the `predicted_*`
   columns while labelling avoids anchoring.

3. **Score.**
   ```bash
   python -m evaluation.score
   ```
   This refuses to run while any verified cell is blank. It writes:
   - `evaluation/eval_results.json`: metrics, every error, ambiguous and unknown cases
   - `evaluation/confusion_matrix.csv`: role confusion matrix (rows = verified, columns = predicted)
   - `evaluation/eval_report.md`: a readable report to paste into this file

4. **Commit** `eval_set.csv` (the labelled dataset, as CSV) and the three outputs.

## Metrics

| Metric | Definition |
|---|---|
| Role accuracy | predicted role == verified role (exact category) |
| City accuracy (exact) | normalized set of predicted cities == normalized set of verified cities (`Remote` and `Unknown` count as values) |
| City accuracy (overlap) | at least one city in common; shows partial credit on multi-city postings |
| Confusion matrix | counts for every (verified, predicted) role pair present |
| Ambiguous cases | rows the reviewer marked `is_ambiguous = yes`, listed with notes |
| Unknown cases | rows where either side is `Unknown` for role or city |

City names on both sides go through the same normalizer (`pipeline/cities.py`), so
"Bangalore" vs "Bengaluru" isn't counted as an error.

## Results

_Pending. Paste `evaluation/eval_report.md` here after step 3._

## Known threats to validity

- **One annotator.** Labels reflect one person's reading. Ambiguous rows are flagged so this can
  be judged.
- **Adzuna snippets.** About 500 characters gives the model less to go on than full ATS
  descriptions. Breaking accuracy down by `source_name` (a column in the CSV) shows the effect.
- **Category boundaries.** Roles like "Data Engineer" or "Mobile Developer" have no category of
  their own. The prompt maps them deliberately (Other, Software Engineer), and labels must use
  the same mapping.
- **Sample size.** 50 postings gives a rough estimate (about ±13 percentage points at 95%
  confidence near 70% accuracy), not a precise one.

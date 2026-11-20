import csv

from evaluation import score as sc
from evaluation.sample import COLUMNS


def _write(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def test_refuses_to_score_blank_labels(tmp_path):
    p = tmp_path / "e.csv"
    _write(p, [{"job_id": 1, "predicted_role": "QA Engineer", "predicted_cities": "Pune"}])
    assert sc.main(["--csv", str(p)]) == 1
    assert not (tmp_path / "eval_results.json").exists()


def test_scores_role_city_and_confusion(tmp_path):
    p = tmp_path / "e.csv"
    _write(p, [
        {"job_id": 1, "predicted_role": "QA Engineer", "predicted_cities": "Bengaluru",
         "verified_role": "qa engineer", "verified_cities": "Bangalore"},
        {"job_id": 2, "predicted_role": "Backend Developer", "predicted_cities": "Pune; Remote",
         "verified_role": "Full Stack Developer", "verified_cities": "Pune", "is_ambiguous": "yes"},
        {"job_id": 3, "predicted_role": "Unknown", "predicted_cities": "Unknown",
         "verified_role": "Other", "verified_cities": "unknown"},
    ])
    assert sc.main(["--csv", str(p)]) == 0
    import json
    res = json.loads((tmp_path / "eval_results.json").read_text())
    assert res["role_correct"] == 1 and res["city_exact_correct"] == 2
    assert abs(res["city_any_overlap_accuracy"] - 1.0) < 1e-9
    assert len(res["ambiguous"]) == 1 and len(res["unknown_cases"]) == 1
    matrix = list(csv.reader((tmp_path / "confusion_matrix.csv").open()))
    assert matrix[0][0].startswith("verified")
    assert "Role accuracy" in (tmp_path / "eval_report.md").read_text()

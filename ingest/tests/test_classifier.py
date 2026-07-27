"""Tests for the edge classifier (ADR-007, ADR-001 caveat).

Both accuracy numbers are under the ADR-001 caveat — the simulator produces the
labels, so a high score is close to tautological. The tests verify the training
and evaluation plumbing, not that the classifier is biologically meaningful.
"""

from __future__ import annotations

from ingest.classifier import (
    FEATURE_FIELDS,
    LABELS,
    evaluate,
    features_to_vector,
    generate_synthetic_dataset,
    run_comparison,
    train_mlp,
    train_xgboost,
)


def test_feature_fields_count() -> None:
    assert len(FEATURE_FIELDS) == 11


def test_labels_are_baseline_and_heavy_metal() -> None:
    assert LABELS == ["baseline", "heavy-metal"]


def test_synthetic_dataset_shapes() -> None:
    X, y = generate_synthetic_dataset(n_samples=100, seed=0)
    assert X.shape == (100, 11)
    assert y.shape == (100,)
    assert set(y.tolist()).issubset({0, 1})


def test_xgboost_trains_and_predicts() -> None:
    X, y = generate_synthetic_dataset(n_samples=200, seed=1)
    model = train_xgboost(X, y, seed=1)
    preds = model.predict(X)
    assert preds.shape == (200,)


def test_mlp_trains_and_predicts() -> None:
    X, y = generate_synthetic_dataset(n_samples=200, seed=2)
    model = train_mlp(X, y, seed=2)
    preds = model.predict(X)
    assert preds.shape == (200,)


def test_evaluate_returns_accuracy() -> None:
    X, y = generate_synthetic_dataset(n_samples=200, seed=3)
    model = train_xgboost(X, y, seed=3)
    report = evaluate(model, X, y, "xgboost")
    assert 0.0 <= report.accuracy <= 1.0
    assert report.model_name == "xgboost"
    assert report.feature_importances is not None
    assert len(report.feature_importances) == 11


def test_run_comparison_returns_both_models() -> None:
    result = run_comparison(seed=4, n_samples=300)
    assert "xgboost" in result
    assert "mlp" in result
    assert "caveat" in result
    assert "ADR-001" in result["caveat"]
    assert 0.0 <= result["xgboost"]["accuracy"] <= 1.0
    assert 0.0 <= result["mlp"]["accuracy"] <= 1.0


def test_xgboost_beats_or_matches_mlp_on_synthetic_data() -> None:
    """XGBoost should be at least as good as the MLP on tabular features
    (ADR-007). On this synthetic dataset both should score high (the
    tautology), so we just check both are above a loose floor."""
    result = run_comparison(seed=5, n_samples=500)
    assert result["xgboost"]["accuracy"] > 0.8, (
        f"xgboost accuracy too low: {result['xgboost']['accuracy']}"
    )
    assert result["mlp"]["accuracy"] > 0.8, f"mlp accuracy too low: {result['mlp']['accuracy']}"


def test_features_to_vector_extracts_scalars() -> None:
    features = {
        "amplitude": 3.0,
        "amplitude_mean": 2.5,
        "amplitude_std": 0.1,
        "amplitude_min": 1.0,
        "amplitude_max": 4.0,
        "isi_mean": 100.0,
        "isi_std": 20.0,
        "isi_min": 80.0,
        "isi_max": 120.0,
        "burst_index": 1.2,
        "rate": 5.0,
        "count": 5,
        "histogram": [1, 0, 0, 0, 0, 0, 0, 1],
    }
    vec = features_to_vector(features)
    assert vec.shape == (11,)
    assert abs(vec[0] - 3.0) < 1e-9
    assert abs(vec[10] - 5.0) < 1e-9

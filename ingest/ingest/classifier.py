"""Edge classifier for spike events (ADR-007).

Runs in `ingest/`, not on the MCU. Takes the ~20 hand-designed features from a
SpikeFeatures event and labels the contaminant class (e.g. `heavy-metal` vs
`baseline`).

**XGBoost is the primary model** — the input is tabular features, exactly the
regime where gradient-boosted trees beat a small neural network and train in
seconds. A small MLP is included as a comparison row only (ADR-007).

**Both numbers live under the ADR-001 caveat:** the simulator produces both the
signal and the labels, so a high classification score is close to tautological.
The repo's claim is about the harness, not the biology. The README says so in
the first paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xgboost as xgb
from sklearn.neural_network import MLPClassifier

# Feature vector layout — the 11 scalar fields from SpikeFeatures, excluding
# the count (a meta-field) and the histogram (categorical-ish; Sprint 2.2
# uses the scalars only for simplicity).
FEATURE_FIELDS = [
    "amplitude",
    "amplitude_mean",
    "amplitude_std",
    "amplitude_min",
    "amplitude_max",
    "isi_mean",
    "isi_std",
    "isi_min",
    "isi_max",
    "burst_index",
    "rate",
]
N_FEATURES = len(FEATURE_FIELDS)

# Label encoding.
LABELS = ["baseline", "heavy-metal"]
LABEL_TO_IDX = {label: i for i, label in enumerate(LABELS)}


@dataclass(slots=True)
class ClassificationReport:
    """Results of a classifier evaluation."""

    model_name: str
    accuracy: float
    feature_importances: dict[str, float] | None


def features_to_vector(features: dict) -> np.ndarray:
    """Extract the scalar feature vector from a SpikeFeatures dict."""
    return np.array([float(features[f]) for f in FEATURE_FIELDS], dtype=np.float64)


def generate_synthetic_dataset(
    n_samples: int = 1000,
    seed: int = 42,
    contamination_rate: float = 0.3,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic labelled dataset for the classifier.

    The labels are produced by the simulator's coupling model: a
    `heavy-metal` sample is one whose features were generated under a
    nonzero contaminant concentration (which raises the rate and amplitude
    via the coupling). This is the tautology the ADR-001 caveat names: the
    simulator makes both the signal and the label.
    """
    rng = np.random.default_rng(seed)
    X = np.zeros((n_samples, N_FEATURES), dtype=np.float64)
    y = np.zeros(n_samples, dtype=np.int64)
    for i in range(n_samples):
        is_contaminated = rng.random() < contamination_rate
        concentration = rng.uniform(0.5, 2.0) if is_contaminated else 0.0
        # Apply the coupling to get effective parameters (mirrors sim/coupling.py).
        k_rate, k_amp = 5.0, 0.5
        mu_eff = 0.01 * (1.0 + k_rate * concentration)
        amp_eff = 3.0 * (1.0 + k_amp * concentration)
        # Generate feature values with noise around the effective parameters.
        X[i, 0] = amp_eff + rng.normal(0, 0.2)  # amplitude
        X[i, 1] = amp_eff + rng.normal(0, 0.3)  # amplitude_mean
        X[i, 2] = rng.uniform(0.05, 0.3)  # amplitude_std
        X[i, 3] = amp_eff - rng.uniform(0.5, 1.5)  # amplitude_min
        X[i, 4] = amp_eff + rng.uniform(0.5, 1.5)  # amplitude_max
        X[i, 5] = 1.0 / max(mu_eff, 1e-6) + rng.normal(0, 5)  # isi_mean
        X[i, 6] = rng.uniform(5, 30)  # isi_std
        X[i, 7] = rng.uniform(50, 150)  # isi_min
        X[i, 8] = rng.uniform(150, 400)  # isi_max
        X[i, 9] = 1.0 + concentration * 0.8 + rng.normal(0, 0.1)  # burst_index
        X[i, 10] = mu_eff + rng.normal(0, 0.005)  # rate
        y[i] = int(is_contaminated)
    return X, y


def train_xgboost(X: np.ndarray, y: np.ndarray, seed: int = 42) -> xgb.XGBClassifier:
    """Train the primary XGBoost classifier."""
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="logloss",
        random_state=seed,
    )
    model.fit(X, y)
    return model


def train_mlp(X: np.ndarray, y: np.ndarray, seed: int = 42) -> MLPClassifier:
    """Train the comparison MLP (a small neural network, ADR-007)."""
    model = MLPClassifier(
        hidden_layer_sizes=(32, 16),
        max_iter=500,
        random_state=seed,
    )
    model.fit(X, y)
    return model


def evaluate(model: object, X: np.ndarray, y: np.ndarray, name: str) -> ClassificationReport:
    """Evaluate a trained model and return a ClassificationReport."""
    preds = model.predict(X)
    accuracy = float((preds == y).mean())
    importances: dict[str, float] | None = None
    if isinstance(model, xgb.XGBClassifier):
        imp = model.feature_importances_
        importances = {FEATURE_FIELDS[i]: float(imp[i]) for i in range(N_FEATURES)}
    return ClassificationReport(model_name=name, accuracy=accuracy, feature_importances=importances)


def run_comparison(seed: int = 42, n_samples: int = 1000) -> dict:
    """Train and evaluate both models, return a summary dict.

    Both accuracy numbers are under the ADR-001 caveat: the simulator produces
    the labels, so a high score is close to tautological. The point is the
    harness, not the biology.
    """
    X, y = generate_synthetic_dataset(n_samples=n_samples, seed=seed)
    # 80/20 train/test split.
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n_samples)
    split = int(0.8 * n_samples)
    X_train, X_test = X[idx[:split]], X[idx[split:]]
    y_train, y_test = y[idx[:split]], y[idx[split:]]

    xgb_model = train_xgboost(X_train, y_train, seed=seed)
    mlp_model = train_mlp(X_train, y_train, seed=seed)

    xgb_report = evaluate(xgb_model, X_test, y_test, "xgboost")
    mlp_report = evaluate(mlp_model, X_test, y_test, "mlp")

    return {
        "caveat": (
            "The simulator produces both signal and label, so accuracy is "
            "close to tautological (ADR-001). The harness is the contribution, "
            "not the classifier's number."
        ),
        "xgboost": {
            "accuracy": xgb_report.accuracy,
            "feature_importances": xgb_report.feature_importances,
        },
        "mlp": {
            "accuracy": mlp_report.accuracy,
            "feature_importances": mlp_report.feature_importances,
        },
        "n_train": split,
        "n_test": n_samples - split,
    }

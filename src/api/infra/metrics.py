"""Low-cardinality Prometheus metrics for the service."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "credit_scoring_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "endpoint", "status_code"],
)
HTTP_ERRORS = Counter(
    "credit_scoring_http_errors_total",
    "HTTP responses with a client or server error status.",
    ["method", "endpoint", "status_code"],
)
HTTP_LATENCY = Histogram(
    "credit_scoring_http_request_duration_seconds",
    "End-to-end HTTP request latency.",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
INFERENCE_LATENCY = Histogram(
    "credit_scoring_inference_duration_seconds",
    "In-memory model inference latency.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)
MODEL_INFO = Gauge(
    "credit_scoring_model_info",
    "Champion model currently loaded, set to 1 once at startup.",
    ["model_version", "model_alias"],
)
MLFLOW_ERRORS = Counter("credit_scoring_mlflow_errors_total", "MLflow startup failures.")
POSTGRES_ERRORS = Counter(
    "credit_scoring_postgres_errors_total", "PostgreSQL availability failures."
)
PREDICTION_SCORE = Histogram(
    "credit_scoring_prediction_probability",
    "Predicted positive-class probability.",
    buckets=(
        0.05,
        0.1,
        0.15,
        0.2,
        0.25,
        0.3,
        0.35,
        0.4,
        0.45,
        0.5,
        0.55,
        0.6,
        0.65,
        0.7,
        0.75,
        0.8,
        0.85,
        0.9,
        0.95,
        1.0,
    ),
)
PREDICTION_DECISIONS = Counter(
    "credit_scoring_prediction_decisions_total",
    "Predictions by decision.",
    ["decision"],
)

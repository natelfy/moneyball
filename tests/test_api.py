from fastapi.testclient import TestClient

from api import ProspectStats, app, build_feature_frame, get_model, to_scout_scale
from features import MODEL_FEATURE_COLUMNS


class _StubModel:
    """Modèle factice : renvoie une FV fixe, sans dépendre de S3."""
    def __init__(self, value=57.3):
        self.value = value
        self.received = None

    def predict(self, features):
        self.received = features
        return [self.value]


def _client(stub):
    app.dependency_overrides[get_model] = lambda: stub
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_predict_returns_raw_and_rounded_fv():
    stub = _StubModel(57.3)
    client = _client(stub)
    payload = {
        "games_played": 57, "at_bats": 200, "hits": 70, "home_runs": 34,
        "walks": 25, "strikeouts": 60, "hit_grade": 55, "power_grade": 70,
        "run_grade": 40, "arm_grade": 55, "field_grade": 50,
    }
    resp = client.post("/predict", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["predicted_fv"] == 57.3
    assert body["rounded_fv"] == 55  # 57.3 -> multiple de 5 le plus proche
    # Le modèle a bien reçu le vecteur de features complet, dans l'ordre.
    assert list(stub.received.columns) == MODEL_FEATURE_COLUMNS


def test_predict_validates_input():
    # Le stub évite tout appel S3 ; on vérifie que la validation Pydantic
    # rejette une note hors échelle 20-80 avant toute prédiction.
    client = _client(_StubModel())
    resp = client.post("/predict", json={"at_bats": 100, "hit_grade": 99})
    assert resp.status_code == 422


def test_to_scout_scale_rounds_and_clamps():
    assert to_scout_scale(57.3) == 55
    assert to_scout_scale(58.0) == 60
    assert to_scout_scale(5.0) == 20    # borne basse
    assert to_scout_scale(999.0) == 80  # borne haute


def test_build_feature_frame_includes_sabermetrics():
    stats = ProspectStats(at_bats=200, hits=70, home_runs=34, walks=25, strikeouts=60)
    frame = build_feature_frame(stats)
    assert list(frame.columns) == MODEL_FEATURE_COLUMNS
    assert frame.loc[0, "batting_avg"] == 0.35


def test_rank_endpoint_orders_prospects():
    # /rank ne dépend pas du modèle S3 : scoring statistique pur.
    client = TestClient(app)
    payload = {"prospects": [
        {"player_name": "Weak", "team": "B", "games_played": 57, "home_runs": 5},
        {"player_name": "Slugger", "team": "A", "games_played": 57, "home_runs": 34},
    ]}
    resp = client.post("/rank", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["ranking"][0]["player_name"] == "Slugger"  # meilleure FV en tête
    assert body["ranking"][0]["overall_fv"] >= body["ranking"][1]["overall_fv"]


def test_valuation_endpoint_flags_undervalued():
    client = TestClient(app)
    payload = {
        "games_played": 57, "at_bats": 200, "hits": 78, "home_runs": 34,
        "walks": 40, "strikeouts": 30, "scout_hit_grade": 40, "scout_power_grade": 40,
    }
    resp = client.post("/valuation", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == "UNDERVALUED"
    assert body["gap"] > 0

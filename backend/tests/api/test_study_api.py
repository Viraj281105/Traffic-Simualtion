from fastapi.testclient import TestClient

from src.database.db import init_db
from src.main import app

client = TestClient(app)


def test_api_study_endpoints(tmp_path, monkeypatch) -> None:
    test_db = str(tmp_path / "test_api_study.db")
    monkeypatch.setattr("src.database.db.DB_PATH", test_db)
    monkeypatch.setattr("src.study.volume_sweep.DB_PATH", test_db)
    monkeypatch.setattr("src.main.DB_PATH", test_db)

    init_db()

    # 1. Run Sweep Endpoint
    sweep_payload = {
        "arrivalRates": [0.2, 0.4],
        "duration": 4.0,
        "randomSeed": 42,
        "name": "API Sweep Test",
    }
    res_sweep = client.post("/api/v1/study/sweeps/run", json=sweep_payload)
    assert res_sweep.status_code == 200
    sweep_data = res_sweep.json()
    assert sweep_data["name"] == "API Sweep Test"
    session_id = sweep_data["sessionId"]

    # 2. List Sweeps
    res_list_sweeps = client.get("/api/v1/study/sweeps")
    assert res_list_sweeps.status_code == 200
    sweeps_list = res_list_sweeps.json()
    assert len(sweeps_list) >= 1
    assert any(s["id"] == session_id for s in sweeps_list)

    # 3. Get Specific Sweep
    res_get_sweep = client.get(f"/api/v1/study/sweeps/{session_id}")
    assert res_get_sweep.status_code == 200
    sweep_body = res_get_sweep.json()
    assert sweep_body["id"] == session_id
    assert sweep_body["sessionId"] == session_id
    assert "runs" in sweep_body
    assert "curves" in sweep_body

    # 4. List Simulation Runs
    res_runs = client.get("/api/v1/study/history/runs")
    assert res_runs.status_code == 200
    runs_list = res_runs.json()
    assert len(runs_list) >= 1

    # 5. Get Specific Simulation Run
    run_id = runs_list[0]["id"]
    res_run = client.get(f"/api/v1/study/history/runs/{run_id}")
    assert res_run.status_code == 200
    assert res_run.json()["run"]["id"] == run_id

    # 6. Validate Repeatability
    res_rep = client.post(
        "/api/v1/study/validate/repeatability",
        json={"duration": 3.0, "randomSeed": 101},
    )
    assert res_rep.status_code == 200
    assert res_rep.json()["valid"] is True
    assert res_rep.json()["isDeterministic"] is True

    # 7. Validate Monte Carlo
    res_mc = client.post(
        "/api/v1/study/validate/monte-carlo", json={"numSeeds": 2, "duration": 3.0}
    )
    assert res_mc.status_code == 200
    assert res_mc.json()["numSeeds"] == 2

    # 8. Export Study Report JSON
    res_exp_json = client.get("/api/v1/study/export?format=json")
    assert res_exp_json.status_code == 200
    assert res_exp_json.json()["version"] == "1.0.0"

    # 9. Export Study Report CSV
    res_exp_csv = client.get("/api/v1/study/export?format=csv")
    assert res_exp_csv.status_code == 200
    assert "text/csv" in res_exp_csv.headers["content-type"]
    assert "=== COMPREHENSIVE TRAFFIC STUDY REPORT ===" in res_exp_csv.text

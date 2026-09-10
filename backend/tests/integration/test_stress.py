from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_stress_massive_density() -> None:
    """Verifies backend runs correctly under stress constraints of massive arrival rates and vehicle volumes."""
    config = {
        "simulation": {
            "timeStep": 0.1,
            "duration": 5.0,  # 50 ticks
            "warmupTime": 1.0,
            "randomSeed": 42,
        },
        "traffic": {
            "arrivalRate": 5.0,  # extremely high rate
            "totalVehicles": 500,  # high count limit
        },
        "geometry": {
            "intersectionType": "fixed_time_signal",
            "intersectionCenter": {"x": 0.0, "y": 0.0},
            "boundingRadius": 15.0,
        },
        "controller": {
            "greenTime": 30,
            "yellowTime": 5,
            "allRedTime": 2,
        },
    }

    # Verify creation under stress parameters succeeds
    res_create = client.post("/api/v1/simulations", json=config)
    assert res_create.status_code == 201
    sim_id = res_create.json()["simulationId"]

    # Start run
    res_start = client.post(
        f"/api/v1/simulations/{sim_id}/control", json={"action": "start"}
    )
    assert res_start.status_code == 200

    # Retrieve report in JSON format
    res_json = client.get(f"/api/v1/simulations/{sim_id}/report?format=json")
    assert res_json.status_code == 200
    report_json = res_json.json()
    assert report_json["simulationId"] == sim_id
    assert "masterEfficiencyScore" in report_json["finalMetrics"]

    # Retrieve report in CSV format
    res_csv = client.get(f"/api/v1/simulations/{sim_id}/report?format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert "masterEfficiencyScore" in res_csv.text

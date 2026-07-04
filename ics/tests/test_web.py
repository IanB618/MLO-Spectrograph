from src.web import create_app


def test_status_endpoint():
    app = create_app()
    app.config.update({"TESTING": True})
    client = app.test_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "offline"


def test_connect_endpoint():
    app = create_app()
    app.config.update({"TESTING": True})
    client = app.test_client()
    response = client.post("/api/connect")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "idle"
    assert payload["science_camera"]["connected"] is True

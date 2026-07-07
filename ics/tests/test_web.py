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


def test_exposure_rejects_invalid_binning():
    app = create_app()
    app.config.update({"TESTING": True})
    client = app.test_client()
    client.post("/api/connect")
    response = client.post(
        "/api/science-camera/expose",
        json={
            "exposure_s": 0.1,
            "image_type": "light",
            "object_name": "Test",
            "binning": "3x3",
        },
    )
    assert response.status_code == 400


def test_exposure_accepts_dropdown_binning():
    app = create_app()
    app.config.update({"TESTING": True})
    client = app.test_client()
    client.post("/api/connect")
    response = client.post(
        "/api/science-camera/expose",
        json={
            "exposure_s": 0.1,
            "image_type": "light",
            "object_name": "Test",
            "binning": "2x2",
        },
    )
    assert response.status_code == 200
    status = client.get("/api/status").get_json()
    assert status["science_camera"]["binning"] == [2, 2]

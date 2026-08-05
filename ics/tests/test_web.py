from pathlib import Path

from astropy.io import fits

from src.models import ExposureResult, ExposureType
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


def test_timeout_error_returns_json(monkeypatch):
    app = create_app()
    app.config.update({"TESTING": True, "PROPAGATE_EXCEPTIONS": False})
    client = app.test_client()
    supervisor = app.extensions["ics_supervisor"]

    def raise_timeout():
        raise TimeoutError("Timed out waiting for INDI device 'FLI Kepler'")

    monkeypatch.setattr(supervisor, "connect_all", raise_timeout)
    response = client.post("/api/connect")
    payload = response.get_json()

    assert response.status_code == 504
    assert payload["error"] == "INDI device timeout"
    assert payload["type"] == "TimeoutError"
    assert "<!doctype html>" not in response.get_data(as_text=True).lower()


def test_index_embeds_js9_and_full_width_science_card():
    app = create_app()
    app.config.update({"TESTING": True})
    response = app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "js9-allinone.css" in html
    assert "js9-allinone.js" in html
    assert "css/js9-dark.css" in html
    assert '<body class="ics-dark">' in html
    assert 'id="scienceJS9"' in html
    app_js = (Path(__file__).parents[1] / "src/static/js/app.js").read_text()
    js9_dark_css = (Path(__file__).parents[1] / "src/static/css/js9-dark.css").read_text()
    assert "ResizeDisplay" in app_js
    assert "ResizeObserver" in app_js
    assert "background-color: transparent !important;" in js9_dark_css
    assert "These containers must remain transparent" in js9_dark_css
    assert 'class="card span-2 science-camera-card"' in html


def test_lens_controls_place_aperture_beside_absolute_focus():
    app = create_app()
    app.config.update({"TESTING": True})
    html = app.test_client().get("/").get_data(as_text=True)

    lens_section = html.split("Camera Lens Focus / Pinefeat EF", 1)[1].split(
        "Recent observation log", 1
    )[0]
    assert "Relative delta" not in lens_section
    assert 'class="control-panel two-col-form lens-control-grid"' in lens_section
    assert lens_section.index('id="lens-form"') < lens_section.index(
        'id="lens-aperture-absolute-form"'
    )
    assert 'name="position"' in lens_section
    assert 'name="f_stop"' in lens_section


def test_latest_science_fits_returns_404_without_exposure():
    app = create_app()
    app.config.update({"TESTING": True})
    response = app.test_client().get("/api/science-camera/latest.fits")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Not Found"


def test_latest_science_fits_serves_current_exposure(monkeypatch, tmp_path):
    monkeypatch.setenv("ICS_DATA_ROOT", str(tmp_path))
    app = create_app()
    app.config.update({"TESTING": True})
    supervisor = app.extensions["ics_supervisor"]

    fits_path = tmp_path / "2026-08-04" / "science-test.fits"
    fits_path.parent.mkdir(parents=True)
    fits.PrimaryHDU([[1, 2], [3, 4]]).writeto(fits_path)
    supervisor.last_exposure = ExposureResult(
        exposure_id="science-test",
        image_type=ExposureType.LIGHT,
        exposure_s=1.0,
        path=fits_path,
        success=True,
        message="complete",
    )

    response = app.test_client().get(
        "/api/science-camera/latest.fits?exposure_id=science-test"
    )

    assert response.status_code == 200
    assert response.mimetype == "application/fits"
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert response.data.startswith(b"SIMPLE")


def test_latest_science_fits_rejects_stale_exposure_id(monkeypatch, tmp_path):
    monkeypatch.setenv("ICS_DATA_ROOT", str(tmp_path))
    app = create_app()
    app.config.update({"TESTING": True})
    supervisor = app.extensions["ics_supervisor"]

    fits_path = tmp_path / "2026-08-04" / "science-current.fits"
    fits_path.parent.mkdir(parents=True)
    fits.PrimaryHDU([[1]]).writeto(fits_path)
    supervisor.last_exposure = ExposureResult(
        exposure_id="science-current",
        image_type=ExposureType.LIGHT,
        exposure_s=1.0,
        path=fits_path,
        success=True,
        message="complete",
    )

    response = app.test_client().get(
        "/api/science-camera/latest.fits?exposure_id=science-stale"
    )

    assert response.status_code == 409


def test_science_preview_uses_completed_result_and_refreshes_loaded_image():
    project_root = Path(__file__).parents[1]
    app_js = (project_root / "src/static/js/app.js").read_text()
    base_html = (project_root / "src/templates/base.html").read_text()

    assert "syncSciencePreview(result);" in app_js
    assert 'requestUrl.searchParams.set("revision"' in app_js
    assert "Date.now()" in app_js
    assert "const refreshImage = sciencePreviewState.image;" in app_js
    assert "refresh: refreshImage || false" in app_js
    assert "refresh: force" not in app_js
    assert "20260804-js9-refresh-object" in base_html



def test_latest_science_fits_rejects_path_outside_data_root(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    outside_path = tmp_path / "outside.fits"
    data_root.mkdir()
    fits.PrimaryHDU([[1]]).writeto(outside_path)
    monkeypatch.setenv("ICS_DATA_ROOT", str(data_root))

    app = create_app()
    app.config.update({"TESTING": True})
    supervisor = app.extensions["ics_supervisor"]
    supervisor.last_exposure = ExposureResult(
        exposure_id="outside",
        image_type=ExposureType.LIGHT,
        exposure_s=1.0,
        path=Path(outside_path),
        success=True,
        message="complete",
    )

    response = app.test_client().get("/api/science-camera/latest.fits")

    assert response.status_code == 404

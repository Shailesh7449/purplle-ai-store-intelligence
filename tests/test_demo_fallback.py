from fastapi.testclient import TestClient
from backend.main_lite import app

def test_video_source():
    client = TestClient(app)
    response = client.get("/api/video-source")
    assert response.status_code == 200
    data = response.json()
    assert "source" in data
    assert data["source"] in ("generated", "demo")

def test_tracked_video_fallback():
    client = TestClient(app)
    response = client.get("/tracked_store.mp4")
    assert response.status_code == 200
    assert response.headers.get("X-Video-Source") in ("generated", "demo")

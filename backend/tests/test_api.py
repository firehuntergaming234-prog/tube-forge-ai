from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True

def test_upload_rejects_unsupported_extension():
    r = client.post("/api/upload", files={"file": ("notes.txt", b"not a video", "text/plain")})
    assert r.status_code == 415

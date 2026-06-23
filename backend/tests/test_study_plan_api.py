import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.repository import MemoryRepository
from app.services.auth import create_access_token
from app.services.study import StudyService


@pytest.fixture()
def study_plan_api(monkeypatch):
    repo = MemoryRepository()
    user = repo.create_user("student@example.com", "hash")
    monkeypatch.setattr(main_module, "repo", repo)
    monkeypatch.setattr(main_module, "study", StudyService(repo, None))
    token = create_access_token(user["id"], main_module.settings.jwt_secret, 10)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(main_module.app) as client:
        yield client, repo, user, headers


def test_get_study_plan_does_not_save_duplicate_rows(study_plan_api):
    client, repo, user, headers = study_plan_api

    first = client.get("/api/study-plan", headers=headers)
    second = client.get("/api/study-plan", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["metadata"] == {"source": "empty_state"}
    assert first.json()["id"] is None
    assert second.json()["id"] is None
    assert len(repo.list_study_plans(user["id"])) == 0


def test_post_study_plan_creates_saved_plan(study_plan_api):
    client, repo, user, headers = study_plan_api

    response = client.post("/api/study-plan", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"]
    assert body["metadata"] == {"source": "empty_state"}
    assert len(repo.list_study_plans(user["id"])) == 1
    assert repo.list_study_plans(user["id"])[0]["id"] == body["id"]


def test_get_study_plan_after_post_returns_latest_saved_plan(study_plan_api):
    client, repo, user, headers = study_plan_api
    older = repo.save_study_plan(user["id"], ["Older plan"], ["older"], {"source": "test"})
    repo.study_plans[older["id"]]["created_at"] = "2000-01-01T00:00:00+00:00"

    created = client.post("/api/study-plan", headers=headers).json()
    response = client.get("/api/study-plan", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["plan"] == created["plan"]
    assert response.json()["id"] != older["id"]
    assert len(repo.list_study_plans(user["id"])) == 2

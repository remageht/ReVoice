"""
Тесты health endpoint и базовых маршрутов.
"""
from __future__ import annotations
import pytest
from httpx import AsyncClient, ASGITransport

from revoice.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "gpu" in data


@pytest.mark.asyncio
async def test_models_list():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Real engine present
        ids = [m["engine_id"] for m in data]
        assert "qwen" in ids


@pytest.mark.asyncio
async def test_profiles_crud():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        r = await client.post("/api/profiles", json={
            "name": "Тестовый голос",
            "description": "Автотест",
            "language": "ru",
        })
        assert r.status_code == 201, r.text
        profile = r.json()
        pid = profile["id"]
        assert profile["name"] == "Тестовый голос"

        # Get
        r2 = await client.get(f"/api/profiles/{pid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == pid

        # Update
        r3 = await client.patch(f"/api/profiles/{pid}", json={"name": "Обновлённый"})
        assert r3.status_code == 200
        assert r3.json()["name"] == "Обновлённый"

        # List
        r4 = await client.get("/api/profiles")
        assert r4.status_code == 200
        ids = [p["id"] for p in r4.json()]
        assert pid in ids

        # Delete
        r5 = await client.delete(f"/api/profiles/{pid}")
        assert r5.status_code == 204

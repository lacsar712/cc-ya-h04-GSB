"""H04 链路集成测试：入队落盘 → 列表顶序 → 同机最近查询。

需要可连的 PostgreSQL（DATABASE_URL，默认 postgresql://app:app@localhost:54399/yawalign）。
连不上时整个模块 skip。
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="未设置 DATABASE_URL，跳过数据库集成测试",
)

from api import app  # noqa: E402
from db import SCHEMA, connect  # noqa: E402


def _reset_db():
    with connect() as conn:
        conn.execute(SCHEMA)
        conn.execute("TRUNCATE yaw_logs RESTART IDENTITY")
        conn.commit()


@pytest.fixture(autouse=True)
def _clean():
    _reset_db()
    yield
    _reset_db()


async def _client_and_token(role: str):
    client = app.test_client()
    await client.__aenter__()
    cred = {
        "writer": ("technician", "tech123456"),
        "reader": ("observer", "obs123456"),
    }[role]
    resp = await client.post(
        "/api/auth/login", json={"username": cred[0], "password": cred[1]}
    )
    token = (await resp.get_json())["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def _run(coro):
    return asyncio.run(coro)


def test_list_order_is_newest_first():
    async def scenario():
        client, headers = await _client_and_token("writer")
        try:
            first = await client.post(
                "/api/logs",
                json={"turbine_code": "W01", "yaw_err_deg": 0.4},
                headers=headers,
            )
            second = await client.post(
                "/api/logs",
                json={"turbine_code": "W02", "yaw_err_deg": 3.2},
                headers=headers,
            )
            id_first = (await first.get_json())["id"]
            id_second = (await second.get_json())["id"]
            assert id_second > id_first

            resp = await client.get("/api/logs", headers=headers)
            rows = await resp.get_json()
            assert resp.status_code == 200
            ids = [r["id"] for r in rows]
            # 新单必须在列表顶部，整体严格按 id 倒序
            assert ids[0] == id_second
            assert ids == sorted(ids, reverse=True)
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_same_turbine_latest_returns_newest_not_oldest():
    async def scenario():
        client, headers = await _client_and_token("writer")
        try:
            old = await client.post(
                "/api/logs",
                json={"turbine_code": "W05", "yaw_err_deg": 2.0},
                headers=headers,
            )
            old_id = (await old.get_json())["id"]
            new = await client.post(
                "/api/logs",
                json={"turbine_code": "W05", "yaw_err_deg": -0.3},
                headers=headers,
            )
            new_id = (await new.get_json())["id"]
            assert new_id > old_id

            resp = await client.get(
                "/api/logs/latest?turbine_code=W05", headers=headers
            )
            assert resp.status_code == 200
            row = await resp.get_json()
            # 同机查询必须捞到最新编号，不能答旧号
            assert row["id"] == new_id
            assert row["turbine_code"] == "W05"
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_enqueue_instant_three_ways_consistent():
    """入队瞬间：POST 应答、列表顶部、同机最近，三处编号必须一致。"""

    async def scenario():
        client, headers = await _client_and_token("writer")
        try:
            # 该机已有一张旧单
            old = await client.post(
                "/api/logs",
                json={"turbine_code": "W09", "yaw_err_deg": 2.5},
                headers=headers,
            )
            old_id = (await old.get_json())["id"]

            resp = await client.post(
                "/api/logs",
                json={"turbine_code": "W09", "yaw_err_deg": 0.9},
                headers=headers,
            )
            assert resp.status_code == 201
            created = await resp.get_json()
            new_id = created["id"]
            assert new_id != old_id
            assert created["status"] == "pending"

            list_resp = await client.get("/api/logs", headers=headers)
            list_rows = await list_resp.get_json()
            assert list_rows[0]["id"] == new_id
            assert list_rows[0]["status"] == "pending"

            latest_resp = await client.get(
                "/api/logs/latest?turbine_code=W09", headers=headers
            )
            latest_row = await latest_resp.get_json()
            assert latest_row["id"] == new_id
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_latest_on_unknown_turbine_has_no_fabricated_id():
    async def scenario():
        client, headers = await _client_and_token("writer")
        try:
            resp = await client.get(
                "/api/logs/latest?turbine_code=W-NEVER", headers=headers
            )
            assert resp.status_code == 404
            body = await resp.get_json()
            # 无单据时只如实报 404，绝不编造编号
            assert "id" not in body
            assert "turbine_code" not in body
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_latest_requires_code():
    async def scenario():
        client, headers = await _client_and_token("writer")
        try:
            resp = await client.get("/api/logs/latest", headers=headers)
            assert resp.status_code == 400
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_observer_read_only_can_query_latest():
    async def scenario():
        writer_client, writer_headers = await _client_and_token("writer")
        try:
            created = await writer_client.post(
                "/api/logs",
                json={"turbine_code": "W07", "yaw_err_deg": 3.2},
                headers=writer_headers,
            )
            new_id = (await created.get_json())["id"]
        finally:
            await writer_client.__aexit__(None, None, None)

        client, headers = await _client_and_token("reader")
        try:
            # observer 可看列表、可查同机最近
            list_resp = await client.get("/api/logs", headers=headers)
            assert list_resp.status_code == 200
            assert (await list_resp.get_json())[0]["id"] == new_id

            latest_resp = await client.get(
                "/api/logs/latest?turbine_code=W07", headers=headers
            )
            assert latest_resp.status_code == 200
            assert (await latest_resp.get_json())["id"] == new_id

            # observer 仍只读，不可报送
            denied = await client.post(
                "/api/logs",
                json={"turbine_code": "W07", "yaw_err_deg": 0.1},
                headers=headers,
            )
            assert denied.status_code == 403
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())


def test_anonymous_rejected():
    async def scenario():
        client = app.test_client()
        await client.__aenter__()
        try:
            assert (await client.get("/api/logs")).status_code == 401
            assert (
                await client.get("/api/logs/latest?turbine_code=W01")
            ).status_code == 401
        finally:
            await client.__aexit__(None, None, None)

    _run(scenario())

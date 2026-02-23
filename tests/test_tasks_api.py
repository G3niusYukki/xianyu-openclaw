"""
任务管理 API 测试
Task API Tests
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.api import app, scheduler_service


@pytest.fixture
def task_api_client(temp_dir):
    """提供隔离的任务 API 客户端"""
    original_task_file = scheduler_service.task_file
    original_tasks = scheduler_service.tasks.copy()

    scheduler_service.task_file = Path(temp_dir) / "scheduler_tasks_test.json"
    scheduler_service.tasks = {}

    client = TestClient(app)
    try:
        yield client
    finally:
        scheduler_service.tasks = {}
        scheduler_service.task_file = original_task_file
        scheduler_service.tasks = original_tasks


def test_task_crud_and_run(task_api_client: TestClient):
    """测试任务创建、执行、启停、删除全流程"""
    create_resp = task_api_client.post(
        "/api/tasks",
        json={
            "task_type": "polish",
            "name": "test-polish",
            "cron_expression": "0 9 * * *",
            "enabled": True,
            "params": {"max_items": 3},
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["success"] is True
    task_id = created["data"]["task_id"]

    list_resp = task_api_client.get("/api/tasks")
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["success"] is True
    assert any(t["task_id"] == task_id for t in listed["data"])

    run_resp = task_api_client.post(f"/api/tasks/{task_id}/run")
    assert run_resp.status_code == 200
    assert run_resp.json()["success"] is True

    toggle_resp = task_api_client.post(f"/api/tasks/{task_id}/toggle", params={"enabled": "false"})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["success"] is True

    status_resp = task_api_client.get("/api/tasks/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["success"] is True

    delete_resp = task_api_client.delete(f"/api/tasks/{task_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True


def test_create_task_invalid_type(task_api_client: TestClient):
    """测试无效任务类型校验"""
    resp = task_api_client.post(
        "/api/tasks",
        json={
            "task_type": "invalid-task-type",
            "name": "bad-task",
            "enabled": True,
        },
    )
    assert resp.status_code == 400

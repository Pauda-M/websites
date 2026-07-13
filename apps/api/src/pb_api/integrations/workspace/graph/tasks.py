"""Tasks capability over Microsoft Graph (Microsoft To Do and Planner)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pb_api.integrations.workspace.domain.common import utcnow
from pb_api.integrations.workspace.domain.page import Page
from pb_api.integrations.workspace.domain.tasks import (
    WorkspaceTask,
    WorkspaceTaskPriority,
    WorkspaceTaskStatus,
)
from pb_api.integrations.workspace.graph.client import (
    GraphClient,
    parse_graph_datetime,
    to_graph_utc_iso,
)
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver

_TODO_STATUS = {
    "notstarted": WorkspaceTaskStatus.NOT_STARTED,
    "inprogress": WorkspaceTaskStatus.IN_PROGRESS,
    "completed": WorkspaceTaskStatus.COMPLETED,
    "waitingonothers": WorkspaceTaskStatus.IN_PROGRESS,
    "deferred": WorkspaceTaskStatus.DEFERRED,
}
_STATUS_TO_TODO = {
    WorkspaceTaskStatus.NOT_STARTED: "notStarted",
    WorkspaceTaskStatus.IN_PROGRESS: "inProgress",
    WorkspaceTaskStatus.COMPLETED: "completed",
    WorkspaceTaskStatus.DEFERRED: "deferred",
}
_TODO_IMPORTANCE = {
    "low": WorkspaceTaskPriority.LOW,
    "normal": WorkspaceTaskPriority.NORMAL,
    "high": WorkspaceTaskPriority.HIGH,
}
_PRIORITY_TO_IMPORTANCE = {
    WorkspaceTaskPriority.LOW: "low",
    WorkspaceTaskPriority.NORMAL: "normal",
    WorkspaceTaskPriority.HIGH: "high",
}


class GraphTasksProvider:
    """Implements :class:`TaskProvider` against To Do and Planner."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        source: str = "todo",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceTask]:
        user = await self._resolver.default_user(tenant_id, connection_id)
        if source == "planner":
            return await self._client.paginate(
                f"/users/{user}/planner/tasks",
                tenant_id=tenant_id,
                connection_id=connection_id,
                params={"$top": page_size},
                cursor=cursor,
                map_item=lambda item: _planner_to_task(item, tenant_id),
            )
        if cursor:
            return await self._client.paginate(
                "",
                tenant_id=tenant_id,
                connection_id=connection_id,
                cursor=cursor,
                map_item=lambda item: _todo_to_task(item, tenant_id, ""),
            )
        list_id = await self._default_list_id(tenant_id, connection_id, user)
        return await self._client.paginate(
            f"/users/{user}/todo/lists/{list_id}/tasks",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size},
            map_item=lambda item: _todo_to_task(item, tenant_id, list_id),
        )

    async def create_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task: WorkspaceTask
    ) -> str:
        user = await self._resolver.default_user(tenant_id, connection_id)
        if task.source == "planner":
            response = await self._client.post(
                "/planner/tasks",
                tenant_id=tenant_id,
                connection_id=connection_id,
                json=_planner_body(task),
            )
            return str(response.json().get("id", ""))
        list_id = task.list_or_plan_id or await self._default_list_id(
            tenant_id, connection_id, user
        )
        response = await self._client.post(
            f"/users/{user}/todo/lists/{list_id}/tasks",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=_todo_body(task),
        )
        return str(response.json().get("id", ""))

    async def complete_task(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task_provider_id: str
    ) -> None:
        # A bare task id could belong to either backend; try Planner (which needs an
        # ETag concurrency token) and fall back to the To Do default list.
        etag = await self._planner_etag(tenant_id, connection_id, task_provider_id)
        if etag is not None:
            await self._client.patch(
                f"/planner/tasks/{task_provider_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
                json={"percentComplete": 100},
                headers={"If-Match": etag},
            )
            return
        user = await self._resolver.default_user(tenant_id, connection_id)
        list_id = await self._default_list_id(tenant_id, connection_id, user)
        await self._client.patch(
            f"/users/{user}/todo/lists/{list_id}/tasks/{task_provider_id}",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"status": "completed"},
        )

    # -- Internals ------------------------------------------------------

    async def _default_list_id(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, user: str
    ) -> str:
        response = await self._client.get(
            f"/users/{user}/todo/lists",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        lists = response.json().get("value", [])
        if not isinstance(lists, list) or not lists:
            raise GraphError(
                "no To Do lists available for the user",
                status_code=404,
                code="NoTaskList",
            )
        for item in lists:
            if isinstance(item, dict) and item.get("wellknownListName") == "defaultList":
                return str(item.get("id", ""))
        first = lists[0]
        return str(first.get("id", "")) if isinstance(first, dict) else ""

    async def _planner_etag(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, task_provider_id: str
    ) -> str | None:
        try:
            response = await self._client.get(
                f"/planner/tasks/{task_provider_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
        except GraphError as error:
            if error.status_code in (400, 404):
                return None
            raise
        etag = response.json().get("@odata.etag")
        return str(etag) if isinstance(etag, str) and etag else None


def _todo_body(task: WorkspaceTask) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": task.title,
        "body": {"content": task.notes, "contentType": "text"},
        "importance": _PRIORITY_TO_IMPORTANCE.get(task.priority, "normal"),
        "status": _STATUS_TO_TODO.get(task.status, "notStarted"),
    }
    if task.due_at is not None:
        body["dueDateTime"] = {"dateTime": to_graph_utc_iso(task.due_at), "timeZone": "UTC"}
    return body


def _planner_body(task: WorkspaceTask) -> dict[str, Any]:
    body: dict[str, Any] = {"title": task.title}
    if task.list_or_plan_id:
        body["planId"] = task.list_or_plan_id
    if task.due_at is not None:
        body["dueDateTime"] = to_graph_utc_iso(task.due_at)
    if task.assigned_to_provider_ids:
        body["assignments"] = {
            user_id: {
                "@odata.type": "#microsoft.graph.plannerAssignment",
                "orderHint": " !",
            }
            for user_id in task.assigned_to_provider_ids
        }
    return body


def _todo_to_task(data: Any, tenant_id: uuid.UUID, list_id: str) -> WorkspaceTask:
    if not isinstance(data, dict):
        data = {}
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    due = data.get("dueDateTime") if isinstance(data.get("dueDateTime"), dict) else {}
    status = str(data.get("status", "notStarted")).lower()
    importance = str(data.get("importance", "normal")).lower()
    return WorkspaceTask(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        source="todo",
        list_or_plan_id=list_id or None,
        title=str(data.get("title", "")),
        notes=str(body.get("content", "") or ""),
        status=_TODO_STATUS.get(status, WorkspaceTaskStatus.NOT_STARTED),
        priority=_TODO_IMPORTANCE.get(importance, WorkspaceTaskPriority.NORMAL),
        due_at=parse_graph_datetime(due.get("dateTime")),
        completed_at=_completed_at(data.get("completedDateTime")),
        updated_at=parse_graph_datetime(data.get("lastModifiedDateTime")) or utcnow(),
    )


def _planner_to_task(data: Any, tenant_id: uuid.UUID) -> WorkspaceTask:
    if not isinstance(data, dict):
        data = {}
    percent = int(data.get("percentComplete", 0) or 0)
    assignments = data.get("assignments") if isinstance(data.get("assignments"), dict) else {}
    return WorkspaceTask(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        source="planner",
        list_or_plan_id=_optional_str(data.get("planId")),
        title=str(data.get("title", "")),
        status=_planner_status(percent),
        priority=_planner_priority(int(data.get("priority", 5) or 5)),
        assigned_to_provider_ids=[str(key) for key in assignments],
        due_at=parse_graph_datetime(data.get("dueDateTime")),
        completed_at=parse_graph_datetime(data.get("completedDateTime")),
    )


def _planner_status(percent: int) -> WorkspaceTaskStatus:
    if percent >= 100:
        return WorkspaceTaskStatus.COMPLETED
    if percent > 0:
        return WorkspaceTaskStatus.IN_PROGRESS
    return WorkspaceTaskStatus.NOT_STARTED


def _planner_priority(priority: int) -> WorkspaceTaskPriority:
    if priority <= 4:
        return WorkspaceTaskPriority.HIGH
    if priority >= 6:
        return WorkspaceTaskPriority.LOW
    return WorkspaceTaskPriority.NORMAL


def _completed_at(value: Any) -> datetime | None:
    if isinstance(value, dict):
        return parse_graph_datetime(value.get("dateTime"))
    return parse_graph_datetime(value)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None

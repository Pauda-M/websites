"""Synchronization service — keeps Genesis in step with the workspace.

Runs incremental **delta** synchronization per resource: it resumes from the
persisted delta token, walks pages, projects each item into unified search, turns
it into a Genesis event that updates memory, and advances the token. Every run is
recorded as a :class:`SyncJob` for observability; a run that raises is retried with
backoff and, once retries are exhausted, captured in the dead-letter queue so work
is never silently lost (manifesto: Reliability, Observability).
"""

from __future__ import annotations

import asyncio
import builtins
import uuid

from pb_api.core.logging import get_logger
from pb_api.integrations.workspace.application.document_service import DocumentService
from pb_api.integrations.workspace.application.event_projector import WorkspaceEventProjector
from pb_api.integrations.workspace.application.mailbox_service import MailboxService
from pb_api.integrations.workspace.application.search_service import SearchService
from pb_api.integrations.workspace.config import WorkspaceSettings
from pb_api.integrations.workspace.domain.common import SyncResource, SyncStatus, utcnow
from pb_api.integrations.workspace.domain.events import WorkspaceEventType
from pb_api.integrations.workspace.domain.sync import DeadLetter, SyncJob
from pb_api.integrations.workspace.infrastructure.repositories import (
    DeadLetterRepository,
    SyncJobRepository,
    SyncStateRepository,
)
from pb_api.integrations.workspace.ports.providers import WorkspaceProvider

logger = get_logger("pb_api.workspace.sync")


class SyncService:
    def __init__(
        self,
        *,
        provider: WorkspaceProvider,
        mailbox: MailboxService,
        documents: DocumentService,
        search: SearchService,
        projector: WorkspaceEventProjector,
        sync_state: SyncStateRepository,
        sync_jobs: SyncJobRepository,
        dead_letters: DeadLetterRepository,
        settings: WorkspaceSettings,
    ) -> None:
        self._provider = provider
        self._mailbox = mailbox
        self._documents = documents
        self._search = search
        self._projector = projector
        self._sync_state = sync_state
        self._jobs = sync_jobs
        self._dead_letters = dead_letters
        self._settings = settings

    async def sync_resource(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, resource: SyncResource
    ) -> SyncJob:
        """Sync one resource with retry + dead-lettering, recording a SyncJob."""
        job = await self._jobs.add(
            SyncJob(tenant_id=tenant_id, connection_id=connection_id, resource=resource)
        )
        try:
            count = await self._run_with_retry(tenant_id, connection_id, resource)
        except Exception as exc:
            await self._dead_letters.add(
                DeadLetter(
                    tenant_id=tenant_id,
                    kind=f"sync:{resource.value}",
                    payload={"connection_id": str(connection_id)},
                    error=str(exc),
                    attempts=self._settings.max_retries,
                )
            )
            await self._projector.project(
                tenant_id,
                event_type=WorkspaceEventType.SYNC_FAILED,
                summary=f"Sync failed for {resource.value}: {exc}",
                memorize=False,
                payload={"resource": resource.value},
            )
            logger.warning("sync_failed", resource=resource.value, error=str(exc))
            failed = await self._jobs.finish(
                tenant_id, job.id, status=SyncStatus.FAILED, items_processed=0, error=str(exc)
            )
            return failed if failed is not None else job
        finished = await self._jobs.finish(
            tenant_id, job.id, status=SyncStatus.SUCCEEDED, items_processed=count
        )
        return finished if finished is not None else job

    async def _run_with_retry(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, resource: SyncResource
    ) -> int:
        delay = self._settings.retry_base_delay_seconds
        last_exc: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                return await self._dispatch(tenant_id, connection_id, resource)
            except Exception as exc:
                last_exc = exc
                if attempt >= self._settings.max_retries:
                    break
                await asyncio.sleep(min(delay, self._settings.retry_max_delay_seconds))
                delay *= 2
        raise last_exc if last_exc is not None else RuntimeError("sync failed")

    async def _dispatch(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, resource: SyncResource
    ) -> int:
        if resource is SyncResource.MAIL:
            state = await self._mailbox.sync(tenant_id, connection_id)
            return state.items_synced
        if resource is SyncResource.CALENDAR:
            return await self._sync_calendar(tenant_id, connection_id)
        if resource is SyncResource.CONTACTS:
            return await self._sync_contacts(tenant_id, connection_id)
        if resource is SyncResource.DIRECTORY_USERS:
            return await self._sync_directory(tenant_id, connection_id)
        if resource is SyncResource.TASKS:
            return await self._sync_tasks(tenant_id, connection_id)
        return 0

    async def _sync_calendar(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> int:
        state = await self._sync_state.get_or_create(
            tenant_id, connection_id, SyncResource.CALENDAR
        )
        cursor: str | None = None
        processed = 0
        while True:
            page = await self._provider.calendar.delta_events(
                tenant_id, connection_id, delta_token=state.delta_token, cursor=cursor
            )
            for event in page.items:
                await self._search.index_text(
                    tenant_id,
                    kind="meeting",
                    source_provider_id=event.provider_id or str(event.id),
                    title=event.subject,
                    body=event.body,
                    connection_id=connection_id,
                )
                await self._projector.project(
                    tenant_id,
                    event_type=WorkspaceEventType.MEETING_UPDATED,
                    summary=f"Calendar event synced: {event.subject}",
                    memorize=False,
                )
                processed += 1
            if page.delta_token is not None:
                state.delta_token = page.delta_token
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        state.items_synced += processed
        await self._sync_state.update(state)
        return processed

    async def _sync_contacts(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> int:
        state = await self._sync_state.get_or_create(
            tenant_id, connection_id, SyncResource.CONTACTS
        )
        cursor: str | None = None
        processed = 0
        while True:
            page = await self._provider.contacts.delta_contacts(
                tenant_id, connection_id, delta_token=state.delta_token, cursor=cursor
            )
            for contact in page.items:
                await self._search.index_text(
                    tenant_id,
                    kind="contact",
                    source_provider_id=contact.provider_id,
                    title=contact.display_name,
                    body=f"{contact.title or ''} {contact.company or ''} {contact.email or ''}",
                    connection_id=connection_id,
                )
                await self._projector.project(
                    tenant_id,
                    event_type=WorkspaceEventType.CONTACT_UPDATED,
                    summary=f"Contact synced: {contact.display_name}",
                    memorize=False,
                )
                processed += 1
            if page.delta_token is not None:
                state.delta_token = page.delta_token
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        state.items_synced += processed
        await self._sync_state.update(state)
        return processed

    async def _sync_directory(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> int:
        state = await self._sync_state.get_or_create(
            tenant_id, connection_id, SyncResource.DIRECTORY_USERS
        )
        cursor: str | None = None
        processed = 0
        while True:
            page = await self._provider.directory.delta_users(
                tenant_id, connection_id, delta_token=state.delta_token, cursor=cursor
            )
            for user in page.items:
                await self._search.index_text(
                    tenant_id,
                    kind="directory",
                    source_provider_id=user.provider_id,
                    title=user.display_name,
                    body=f"{user.job_title or ''} {user.department or ''} {user.email or ''}",
                    connection_id=connection_id,
                )
                await self._projector.project(
                    tenant_id,
                    event_type=WorkspaceEventType.DIRECTORY_USER_UPDATED,
                    summary=f"Directory user synced: {user.display_name}",
                    memorize=False,
                )
                processed += 1
            if page.delta_token is not None:
                state.delta_token = page.delta_token
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        state.items_synced += processed
        await self._sync_state.update(state)
        return processed

    async def _sync_tasks(self, tenant_id: uuid.UUID, connection_id: uuid.UUID) -> int:
        cursor: str | None = None
        processed = 0
        while True:
            page = await self._provider.tasks.list_tasks(
                tenant_id, connection_id, cursor=cursor, page_size=self._settings.sync_page_size
            )
            for task in page.items:
                await self._search.index_text(
                    tenant_id,
                    kind="task",
                    source_provider_id=task.provider_id,
                    title=task.title,
                    body=task.notes,
                    connection_id=connection_id,
                )
                event_type = (
                    WorkspaceEventType.TASK_COMPLETED
                    if task.status.value == "completed"
                    else WorkspaceEventType.TASK_CREATED
                )
                await self._projector.project(
                    tenant_id,
                    event_type=event_type,
                    summary=f"Task synced: {task.title}",
                    memorize=False,
                )
                processed += 1
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return processed

    async def sync_all(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID
    ) -> builtins.list[SyncJob]:
        """Sync every resource for a connection. Returns the per-resource jobs."""
        resources = [
            SyncResource.MAIL,
            SyncResource.CALENDAR,
            SyncResource.CONTACTS,
            SyncResource.DIRECTORY_USERS,
            SyncResource.TASKS,
        ]
        jobs: builtins.list[SyncJob] = []
        for resource in resources:
            jobs.append(await self.sync_resource(tenant_id, connection_id, resource))
        return jobs

    async def last_jobs(
        self, tenant_id: uuid.UUID, *, connection_id: uuid.UUID | None = None
    ) -> builtins.list[SyncJob]:
        return await self._jobs.list(tenant_id, connection_id=connection_id)

    def _now_iso(self) -> str:
        return utcnow().isoformat()

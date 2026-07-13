"""Mail capability over Microsoft Graph (``/users/{mailbox}/...``)."""

from __future__ import annotations

import uuid
from typing import Any

from pb_api.integrations.workspace.domain.common import (
    AttachmentDisposition,
    MessagePriority,
    utcnow,
)
from pb_api.integrations.workspace.domain.mail import (
    Attachment,
    DraftReply,
    EmailAddress,
    WorkspaceMessage,
)
from pb_api.integrations.workspace.domain.page import DeltaPage, Page
from pb_api.integrations.workspace.graph.client import GraphClient, parse_graph_datetime
from pb_api.integrations.workspace.graph.errors import GraphError
from pb_api.integrations.workspace.graph.resolver import GraphResourceResolver

_IMPORTANCE_TO_PRIORITY = {
    "low": MessagePriority.LOW,
    "normal": MessagePriority.NORMAL,
    "high": MessagePriority.HIGH,
}
_PRIORITY_TO_IMPORTANCE = {
    MessagePriority.LOW: "low",
    MessagePriority.NORMAL: "normal",
    MessagePriority.HIGH: "high",
    MessagePriority.URGENT: "high",
}
_REPLY_ACTION = {
    "reply": "createReply",
    "reply_all": "createReplyAll",
    "forward": "createForward",
}


class GraphMailProvider:
    """Implements :class:`MailProvider` against a Graph mailbox."""

    def __init__(self, client: GraphClient, resolver: GraphResourceResolver) -> None:
        self._client = client
        self._resolver = resolver

    async def list_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        folder: str = "inbox",
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.paginate(
            f"/users/{mailbox}/mailFolders/{folder}/messages",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$top": page_size, "$orderby": "receivedDateTime desc"},
            cursor=cursor,
            map_item=lambda item: _to_message(item, tenant_id, folder=folder),
        )

    async def delta_messages(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        delta_token: str | None = None,
        cursor: str | None = None,
    ) -> DeltaPage[WorkspaceMessage]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.delta(
            f"/users/{mailbox}/mailFolders/inbox/messages",
            tenant_id=tenant_id,
            connection_id=connection_id,
            delta_token=delta_token,
            cursor=cursor,
            map_item=lambda item: _to_message(item, tenant_id, folder="inbox"),
        )

    async def get_message(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> WorkspaceMessage | None:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        try:
            response = await self._client.get(
                f"/users/{mailbox}/messages/{message_provider_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
        except GraphError as error:
            if error.status_code == 404:
                return None
            raise
        return _to_message(response.json(), tenant_id)

    async def get_attachments(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, message_provider_id: str
    ) -> list[Attachment]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        page = await self._client.paginate(
            f"/users/{mailbox}/messages/{message_provider_id}/attachments",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$select": "id,name,contentType,size,isInline,contentId"},
            map_item=_to_attachment,
        )
        return list(page.items)

    async def download_attachment(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        attachment_id: str,
    ) -> bytes:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.get_content(
            f"/users/{mailbox}/messages/{message_provider_id}/attachments/{attachment_id}/$value",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )

    async def create_draft(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply
    ) -> DraftReply:
        draft_id = await self._persist_draft(tenant_id, connection_id, draft)
        return draft.model_copy(update={"provider_draft_id": draft_id})

    async def send(self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply) -> str:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        draft_id = draft.provider_draft_id or await self._persist_draft(
            tenant_id, connection_id, draft
        )
        await self._client.post(
            f"/users/{mailbox}/messages/{draft_id}/send",
            tenant_id=tenant_id,
            connection_id=connection_id,
        )
        return draft_id

    async def move(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        destination_folder: str,
    ) -> None:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        await self._client.post(
            f"/users/{mailbox}/messages/{message_provider_id}/move",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json={"destinationId": destination_folder},
        )

    async def set_categories(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        categories: list[str],
    ) -> None:
        await self._patch_message(
            tenant_id, connection_id, message_provider_id, {"categories": categories}
        )

    async def set_flag(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        flagged: bool,
    ) -> None:
        flag_status = "flagged" if flagged else "notFlagged"
        await self._patch_message(
            tenant_id, connection_id, message_provider_id, {"flag": {"flagStatus": flag_status}}
        )

    async def set_read(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        is_read: bool,
    ) -> None:
        await self._patch_message(
            tenant_id, connection_id, message_provider_id, {"isRead": is_read}
        )

    async def search(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        *,
        query: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> Page[WorkspaceMessage]:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        return await self._client.paginate(
            f"/users/{mailbox}/messages",
            tenant_id=tenant_id,
            connection_id=connection_id,
            params={"$search": f'"{query}"', "$top": page_size},
            cursor=cursor,
            map_item=lambda item: _to_message(item, tenant_id),
        )

    # -- Internals ------------------------------------------------------

    async def _patch_message(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        message_provider_id: str,
        body: dict[str, Any],
    ) -> None:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        await self._client.patch(
            f"/users/{mailbox}/messages/{message_provider_id}",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=body,
        )

    async def _persist_draft(
        self, tenant_id: uuid.UUID, connection_id: uuid.UUID, draft: DraftReply
    ) -> str:
        mailbox = await self._resolver.mailbox(tenant_id, connection_id)
        action = _REPLY_ACTION.get(draft.kind)
        if action is not None and draft.in_reply_to_provider_id:
            # createReply/createReplyAll/createForward return a draft that already
            # threads (and quotes) the original; we then patch in the body/recipients.
            created = await self._client.post(
                f"/users/{mailbox}/messages/{draft.in_reply_to_provider_id}/{action}",
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            draft_id = str(created.json().get("id", ""))
            await self._client.patch(
                f"/users/{mailbox}/messages/{draft_id}",
                tenant_id=tenant_id,
                connection_id=connection_id,
                json=_draft_patch(draft),
            )
            return draft_id
        created = await self._client.post(
            f"/users/{mailbox}/messages",
            tenant_id=tenant_id,
            connection_id=connection_id,
            json=_draft_message(draft),
        )
        return str(created.json().get("id", ""))


def _draft_patch(draft: DraftReply) -> dict[str, Any]:
    body: dict[str, Any] = {
        "body": {"contentType": "html" if draft.is_html else "text", "content": draft.body},
    }
    if draft.to:
        body["toRecipients"] = [_recipient(address) for address in draft.to]
    if draft.cc:
        body["ccRecipients"] = [_recipient(address) for address in draft.cc]
    if draft.subject:
        body["subject"] = draft.subject
    return body


def _draft_message(draft: DraftReply) -> dict[str, Any]:
    message = _draft_patch(draft)
    message.setdefault("toRecipients", [_recipient(address) for address in draft.to])
    return message


def _recipient(address: EmailAddress) -> dict[str, Any]:
    return {"emailAddress": {"address": address.address, "name": address.name}}


def _to_email_address(data: Any) -> EmailAddress:
    email = data.get("emailAddress", {}) if isinstance(data, dict) else {}
    if not isinstance(email, dict):
        email = {}
    return EmailAddress(
        address=str(email.get("address", "")),
        name=str(email.get("name", "")),
    )


def _to_message(data: Any, tenant_id: uuid.UUID, *, folder: str = "inbox") -> WorkspaceMessage:
    if not isinstance(data, dict):
        data = {}
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    flag = data.get("flag") if isinstance(data.get("flag"), dict) else {}
    importance = str(data.get("importance", "normal")).lower()
    return WorkspaceMessage(
        tenant_id=tenant_id,
        provider_id=str(data.get("id", "")),
        conversation_id=_optional_str(data.get("conversationId")),
        internet_message_id=_optional_str(data.get("internetMessageId")),
        subject=str(data.get("subject", "")),
        body_preview=str(data.get("bodyPreview", "")),
        body=str(body.get("content", "")),
        is_html=str(body.get("contentType", "text")).lower() == "html",
        sender=_to_email_address(data.get("from") or data.get("sender") or {}),
        to=[_to_email_address(item) for item in _as_list(data.get("toRecipients"))],
        cc=[_to_email_address(item) for item in _as_list(data.get("ccRecipients"))],
        received_at=parse_graph_datetime(data.get("receivedDateTime")) or utcnow(),
        priority=_IMPORTANCE_TO_PRIORITY.get(importance, MessagePriority.NORMAL),
        is_read=bool(data.get("isRead", False)),
        is_flagged=str(flag.get("flagStatus", "notFlagged")).lower() == "flagged",
        categories=[str(category) for category in _as_list(data.get("categories"))],
        folder=folder,
        has_attachments=bool(data.get("hasAttachments", False)),
    )


def _to_attachment(data: Any) -> Attachment:
    if not isinstance(data, dict):
        data = {}
    is_inline = bool(data.get("isInline", False))
    return Attachment(
        id=str(data.get("id", "")),
        name=str(data.get("name", "")),
        content_type=str(data.get("contentType", "application/octet-stream")),
        size_bytes=int(data.get("size", 0) or 0),
        disposition=(
            AttachmentDisposition.INLINE if is_inline else AttachmentDisposition.ATTACHMENT
        ),
        content_id=_optional_str(data.get("contentId")),
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None

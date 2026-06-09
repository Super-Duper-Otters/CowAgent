# encoding:utf-8
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert, select

from .config_service import sanitize_sensitive_text
from .db import connect, row_to_dict
from .schema import request_events


@dataclass
class RequestEvent:
    event_id: str
    request_id: str
    openid: str
    channel: str
    event_type: str
    message_type: str = ""
    content: str = ""
    media_id: str = ""
    file_path: str = ""
    source_type: str = ""
    source_id: str = ""
    result: str = ""
    error: str = ""
    created_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def record_request_event(
    *,
    request_id: str,
    openid: str,
    channel: str,
    event_type: str,
    message_type: str = "",
    content: str = "",
    media_id: str = "",
    file_path: str = "",
    source_type: str = "",
    source_id: str = "",
    result: str = "",
    error: str = "",
) -> str:
    event_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            insert(request_events).values(
                event_id=event_id,
                request_id=str(request_id or ""),
                openid=str(openid or ""),
                channel=str(channel or ""),
                event_type=str(event_type or ""),
                message_type=str(message_type or ""),
                content=str(content or ""),
                media_id=str(media_id or ""),
                file_path=str(file_path or ""),
                source_type=str(source_type or ""),
                source_id=str(source_id or ""),
                result=str(result or ""),
                error=sanitize_sensitive_text(error),
                created_at=_now(),
            )
        )
    return event_id


def _row_to_event(row) -> RequestEvent:
    item = row_to_dict(row)
    return RequestEvent(
        event_id=item["event_id"],
        request_id=item.get("request_id") or "",
        openid=item.get("openid") or "",
        channel=item.get("channel") or "",
        event_type=item.get("event_type") or "",
        message_type=item.get("message_type") or "",
        content=item.get("content") or "",
        media_id=item.get("media_id") or "",
        file_path=item.get("file_path") or "",
        source_type=item.get("source_type") or "",
        source_id=item.get("source_id") or "",
        result=item.get("result") or "",
        error=item.get("error") or "",
        created_at=item.get("created_at") or "",
    )


def list_request_events(
    *,
    request_id: str = "",
    openid: str = "",
    event_type: str = "",
    limit: int = 100,
) -> list[RequestEvent]:
    stmt = select(request_events)
    conditions = []
    if request_id:
        conditions.append(request_events.c.request_id == request_id)
    if openid:
        conditions.append(request_events.c.openid == openid)
    if event_type:
        conditions.append(request_events.c.event_type == event_type)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(request_events.c.created_at.asc()).limit(max(1, int(limit or 100)))
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_row_to_event(row) for row in rows]

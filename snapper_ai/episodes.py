"""Episode ingest and retrieval.

The hosting application authenticates the episode builder and supplies
its trusted ``builder_identity``; Snapper verifies that identity against
the episode's recorded builder on every write. Episodes and their events
are durable records — once captured, replay does not depend on the
retention of the operational sources the builder read
(docs/EPISODES.md).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Episode, EpisodeEvent, EpisodeParticipant
from .services import SnapperError, _validate_json

MAX_SUMMARY_BYTES = 64 * 1024
MAX_EVENT_PAYLOAD_BYTES = 16 * 1024
MAX_EVENTS_PER_APPEND = 2000
MAX_EVENTS_PER_EPISODE = 200_000
MAX_PARTICIPANTS_PER_EPISODE = 5000


class InvalidEpisode(SnapperError):
    pass


class EpisodeNotFound(SnapperError):
    pass


class EpisodeClosed(SnapperError):
    pass


class BuilderNotAuthorized(SnapperError):
    pass


@dataclass(frozen=True)
class EpisodeUpdate:
    episode_id: str
    scope: str
    created: bool
    closed: bool
    event_count: int


def _identity(value: Any, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidEpisode(f"{label} must be a non-empty string")
    value = value.strip()
    if len(value) > maximum:
        raise InvalidEpisode(f"{label} exceeds {maximum} characters")
    return value


def _optional_text(value: Any, label: str, maximum: int = 255) -> str:
    if value in (None, ""):
        return ""
    return _identity(value, label, maximum)


def _time(value: Any, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = parse_datetime(value)
    else:
        parsed = None
    if parsed is None:
        raise InvalidEpisode(f"{label} must be an ISO datetime")
    if timezone.is_naive(parsed):
        raise InvalidEpisode(f"{label} must carry a timezone offset")
    return parsed


def _bounded_document(value: Any, label: str, max_bytes: int) -> Dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidEpisode(f"{label} must be an object")
    try:
        _validate_json(value)
    except ValueError as exc:
        raise InvalidEpisode(f"{label}: {exc}") from exc
    size = len(json.dumps(value, separators=(",", ":")))
    if size > max_bytes:
        raise InvalidEpisode(f"{label} exceeds {max_bytes} bytes")
    return value


def _authorized(episode: Episode, builder_identity: str) -> None:
    if episode.builder_identity != builder_identity:
        raise BuilderNotAuthorized(
            f"episode {episode.scope}:{episode.episode_id} belongs to "
            f"builder {episode.builder_identity}"
        )


def open_episode(
    scope: str,
    episode_id: str,
    builder_identity: str,
    started_at,
    label: str = "",
    kind: str = "",
    summary: Optional[Dict] = None,
) -> EpisodeUpdate:
    """Create the episode, or return it unchanged if it already exists.

    Reopening is idempotent for the owning builder so a restarted
    builder resumes cleanly; a closed episode stays closed.
    """
    scope = _identity(scope, "scope", 100)
    episode_id = _identity(episode_id, "episode_id")
    builder_identity = _identity(builder_identity, "builder_identity")
    started = _time(started_at, "started_at")
    label = _optional_text(label, "label")
    kind = _optional_text(kind, "kind", 100)
    summary_doc = _bounded_document(summary, "summary", MAX_SUMMARY_BYTES)

    with transaction.atomic():
        episode, created = Episode.objects.select_for_update().get_or_create(
            scope=scope,
            episode_id=episode_id,
            defaults={
                "builder_identity": builder_identity,
                "started_at": started,
                "label": label,
                "kind": kind,
                "summary": summary_doc,
            },
        )
        if not created:
            _authorized(episode, builder_identity)
        return EpisodeUpdate(
            episode_id=episode.episode_id,
            scope=episode.scope,
            created=created,
            closed=episode.ended_at is not None,
            event_count=episode.event_count,
        )


def append_events(
    scope: str,
    episode_id: str,
    builder_identity: str,
    events: Optional[List[Dict]] = None,
    participants: Optional[List[Dict]] = None,
) -> EpisodeUpdate:
    """Append events and upsert participants on an open episode.

    Each event: ``{time, kind, participant, counterpart?, payload?}``.
    Each participant: ``{id, label?, kind?, born_at?, died_at?,
    detail?}`` — repeated upserts update the named fields only, so the
    builder can report a birth first and a death later.
    """
    scope = _identity(scope, "scope", 100)
    episode_id = _identity(episode_id, "episode_id")
    builder_identity = _identity(builder_identity, "builder_identity")
    events = events or []
    participants = participants or []
    if len(events) > MAX_EVENTS_PER_APPEND:
        raise InvalidEpisode(
            f"append exceeds {MAX_EVENTS_PER_APPEND} events"
        )

    with transaction.atomic():
        try:
            episode = Episode.objects.select_for_update().get(
                scope=scope, episode_id=episode_id
            )
        except Episode.DoesNotExist:
            raise EpisodeNotFound(f"{scope}:{episode_id}")
        _authorized(episode, builder_identity)
        if episode.ended_at is not None:
            raise EpisodeClosed(f"{scope}:{episode_id}")
        if episode.event_count + len(events) > MAX_EVENTS_PER_EPISODE:
            raise InvalidEpisode(
                f"episode exceeds {MAX_EVENTS_PER_EPISODE} events"
            )

        for entry in participants:
            if not isinstance(entry, dict):
                raise InvalidEpisode("participant entries must be objects")
            pid = _identity(entry.get("id"), "participant id")
            fields = {}
            if "label" in entry:
                fields["label"] = _optional_text(
                    entry.get("label"), "participant label"
                )
            if "kind" in entry:
                fields["kind"] = _optional_text(
                    entry.get("kind"), "participant kind", 100
                )
            if entry.get("born_at") is not None:
                fields["born_at"] = _time(
                    entry["born_at"], "participant born_at"
                )
            if entry.get("died_at") is not None:
                fields["died_at"] = _time(
                    entry["died_at"], "participant died_at"
                )
            if "detail" in entry:
                fields["detail"] = _bounded_document(
                    entry.get("detail"), "participant detail",
                    MAX_EVENT_PAYLOAD_BYTES,
                )
            record, made = EpisodeParticipant.objects.get_or_create(
                episode=episode, participant_id=pid, defaults=fields
            )
            if not made and fields:
                for name, value in fields.items():
                    setattr(record, name, value)
                record.save(update_fields=list(fields))
            if made and episode.participants.count() > MAX_PARTICIPANTS_PER_EPISODE:
                raise InvalidEpisode(
                    f"episode exceeds {MAX_PARTICIPANTS_PER_EPISODE} participants"
                )

        rows = []
        seq = episode.event_count
        for entry in events:
            if not isinstance(entry, dict):
                raise InvalidEpisode("event entries must be objects")
            seq += 1
            rows.append(EpisodeEvent(
                episode=episode,
                seq=seq,
                event_time=_time(entry.get("time"), "event time"),
                kind=_identity(entry.get("kind"), "event kind", 100),
                participant_id=_identity(
                    entry.get("participant"), "event participant"
                ),
                counterpart_id=_optional_text(
                    entry.get("counterpart"), "event counterpart"
                ),
                payload=_bounded_document(
                    entry.get("payload"), "event payload",
                    MAX_EVENT_PAYLOAD_BYTES,
                ),
            ))
        if rows:
            EpisodeEvent.objects.bulk_create(rows)
            episode.event_count = seq
            episode.save(update_fields=["event_count", "modified_at"])

        return EpisodeUpdate(
            episode_id=episode.episode_id,
            scope=episode.scope,
            created=False,
            closed=False,
            event_count=episode.event_count,
        )


def close_episode(
    scope: str,
    episode_id: str,
    builder_identity: str,
    ended_at,
    summary: Optional[Dict] = None,
) -> EpisodeUpdate:
    """Stamp the episode's end. Closing a closed episode is idempotent
    for the owning builder; the first recorded end stands."""
    scope = _identity(scope, "scope", 100)
    episode_id = _identity(episode_id, "episode_id")
    builder_identity = _identity(builder_identity, "builder_identity")
    ended = _time(ended_at, "ended_at")

    with transaction.atomic():
        try:
            episode = Episode.objects.select_for_update().get(
                scope=scope, episode_id=episode_id
            )
        except Episode.DoesNotExist:
            raise EpisodeNotFound(f"{scope}:{episode_id}")
        _authorized(episode, builder_identity)
        if episode.ended_at is None:
            episode.ended_at = ended
            update_fields = ["ended_at", "modified_at"]
            if summary is not None:
                episode.summary = _bounded_document(
                    summary, "summary", MAX_SUMMARY_BYTES
                )
                update_fields.append("summary")
            episode.save(update_fields=update_fields)
        return EpisodeUpdate(
            episode_id=episode.episode_id,
            scope=episode.scope,
            created=False,
            closed=True,
            event_count=episode.event_count,
        )


def list_episodes(scope: str, limit: int = 50) -> List[Dict]:
    """Recent episodes of a scope, newest first, without events."""
    scope = _identity(scope, "scope", 100)
    limit = max(1, min(int(limit), 500))
    return [
        {
            "episode_id": e.episode_id,
            "scope": e.scope,
            "label": e.label,
            "kind": e.kind,
            "started_at": e.started_at,
            "ended_at": e.ended_at,
            "event_count": e.event_count,
        }
        for e in Episode.objects.filter(scope=scope)[:limit]
    ]


def episode_record(scope: str, episode_id: str) -> Dict:
    """The complete episode: identity, participants, and the ordered
    event sequence — the record the view renders."""
    scope = _identity(scope, "scope", 100)
    episode_id = _identity(episode_id, "episode_id")
    try:
        episode = Episode.objects.get(scope=scope, episode_id=episode_id)
    except Episode.DoesNotExist:
        raise EpisodeNotFound(f"{scope}:{episode_id}")
    return {
        "episode_id": episode.episode_id,
        "scope": episode.scope,
        "label": episode.label,
        "kind": episode.kind,
        "builder_identity": episode.builder_identity,
        "started_at": episode.started_at,
        "ended_at": episode.ended_at,
        "summary": episode.summary,
        "event_count": episode.event_count,
        "participants": [
            {
                "id": p.participant_id,
                "label": p.label,
                "kind": p.kind,
                "born_at": p.born_at,
                "died_at": p.died_at,
                "detail": p.detail,
            }
            for p in episode.participants.all()
        ],
        "events": [
            {
                "seq": ev.seq,
                "time": ev.event_time,
                "kind": ev.kind,
                "participant": ev.participant_id,
                "counterpart": ev.counterpart_id or None,
                "payload": ev.payload,
            }
            for ev in episode.events.all()
        ],
    }

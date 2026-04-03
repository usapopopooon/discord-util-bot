"""API v1 automod routes (JSON)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.db_helpers as _db
import src.web.security as _security
from src.database.models import (
    AutoModBanList,
    AutoModConfig,
    AutoModLog,
    AutoModRule,
    BanLog,
)
from src.utils import get_resource_lock
from src.web.jwt_auth import get_current_user_jwt

router = APIRouter(prefix="/api/v1", tags=["api-automod"])

_VALID_RULE_TYPES = (
    "username_match",
    "account_age",
    "no_avatar",
    "role_acquired",
    "vc_join",
    "message_post",
    "vc_without_intro",
    "msg_without_intro",
    "role_count",
)
_VALID_ACTIONS = ("ban", "kick", "timeout")
_MAX_TIMEOUT_MINUTES = 40320
_MAX_ACCOUNT_AGE_MINUTES = 20160
_MAX_THRESHOLD_SECONDS = 3600


def _serialize_rule(rule: AutoModRule) -> dict[str, Any]:
    """Serialize an AutoModRule to a JSON-safe dict."""
    return {
        "id": rule.id,
        "guild_id": rule.guild_id,
        "rule_type": rule.rule_type,
        "action": rule.action,
        "pattern": rule.pattern,
        "use_wildcard": rule.use_wildcard,
        "threshold_seconds": rule.threshold_seconds,
        "timeout_duration_seconds": rule.timeout_duration_seconds,
        "required_channel_id": rule.required_channel_id,
        "target_role_ids": rule.target_role_ids.split(",")
        if rule.target_role_ids
        else [],
        "is_enabled": rule.is_enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _channels_to_json(
    channels_map: dict[str, list[tuple[str, str]]],
) -> dict[str, list[dict[str, str]]]:
    """Convert channels_map to JSON-serializable format."""
    return {
        gid: [{"id": cid, "name": cname} for cid, cname in clist]
        for gid, clist in channels_map.items()
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_rule_body(body: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Validate rule creation/update fields.

    Returns ``(fields_dict, "")`` on success or ``(None, error_message)``
    on validation failure.
    """
    rule_type: str = body.get("rule_type", "")
    action: str = body.get("action", "ban")

    if rule_type not in _VALID_RULE_TYPES:
        return None, f"Invalid rule_type: {rule_type}"

    if action not in _VALID_ACTIONS:
        return None, f"Invalid action: {action}"

    # timeout_duration_seconds
    timeout_duration_seconds: int | None = None
    if action == "timeout":
        try:
            timeout_minutes = int(body.get("timeout_duration_minutes", ""))
        except (ValueError, TypeError):
            return None, "timeout_duration_minutes is required for timeout action"
        if timeout_minutes < 1 or timeout_minutes > _MAX_TIMEOUT_MINUTES:
            return None, f"timeout_duration_minutes must be 1-{_MAX_TIMEOUT_MINUTES}"
        timeout_duration_seconds = timeout_minutes * 60

    # pattern for username_match
    pattern: str | None = None
    use_wildcard = False
    if rule_type == "username_match":
        pattern = str(body.get("pattern", "")).strip()
        if not pattern:
            return None, "pattern is required for username_match"
        use_wildcard = bool(body.get("use_wildcard", False))

    # threshold_seconds for account_age
    threshold_seconds: int | None = None
    if rule_type == "account_age":
        try:
            minutes_int = int(body.get("account_age_minutes", ""))
        except (ValueError, TypeError):
            return None, "account_age_minutes is required for account_age"
        if minutes_int < 1 or minutes_int > _MAX_ACCOUNT_AGE_MINUTES:
            return None, f"account_age_minutes must be 1-{_MAX_ACCOUNT_AGE_MINUTES}"
        threshold_seconds = minutes_int * 60

    # threshold_seconds for role_acquired/vc_join/message_post
    if rule_type in ("role_acquired", "vc_join", "message_post"):
        try:
            threshold_seconds = int(body.get("threshold_seconds", ""))
        except (ValueError, TypeError):
            return None, "threshold_seconds is required for this rule_type"
        if threshold_seconds < 1 or threshold_seconds > _MAX_THRESHOLD_SECONDS:
            return None, f"threshold_seconds must be 1-{_MAX_THRESHOLD_SECONDS}"

    # threshold_seconds for role_count (stores role count, 1-100)
    target_role_ids: str | None = None
    if rule_type == "role_count":
        try:
            threshold_seconds = int(body.get("threshold_seconds", ""))
        except (ValueError, TypeError):
            return None, "threshold_seconds (role count) is required for role_count"
        if threshold_seconds < 1 or threshold_seconds > 100:
            return None, "threshold_seconds (role count) must be 1-100"
        raw_ids = body.get("target_role_ids", [])
        if isinstance(raw_ids, str):
            raw_ids = [rid.strip() for rid in raw_ids.split(",") if rid.strip()]
        valid_ids = [rid for rid in raw_ids if str(rid).strip().isdigit()]
        if not valid_ids:
            return None, "target_role_ids is required for role_count"
        if len(valid_ids) < threshold_seconds:
            return None, (
                f"target_role_ids count ({len(valid_ids)}) must be >= "
                f"threshold ({threshold_seconds})"
            )
        target_role_ids = ",".join(str(rid).strip() for rid in valid_ids)

    # required_channel_id for intro rules
    required_channel_id: str | None = None
    if rule_type in ("vc_without_intro", "msg_without_intro"):
        raw = str(body.get("required_channel_id", "")).strip()
        if not raw:
            return None, "required_channel_id is required for this rule_type"
        if not raw.isdigit():
            return None, "required_channel_id must be numeric"
        required_channel_id = raw

    return {
        "rule_type": rule_type,
        "action": action,
        "pattern": pattern,
        "use_wildcard": use_wildcard,
        "threshold_seconds": threshold_seconds,
        "timeout_duration_seconds": timeout_duration_seconds,
        "required_channel_id": required_channel_id,
        "target_role_ids": target_role_ids,
    }, ""


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


@router.get("/automod/rules", response_model=None)
async def api_automod_rules_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List all automod rules."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(AutoModRule).order_by(AutoModRule.guild_id, AutoModRule.created_at)
    )
    rules = list(result.scalars().all())
    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    roles_map = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "rules": [_serialize_rule(r) for r in rules],
            "guilds": guilds_map,
            "channels": _channels_to_json(channels_map),
            "roles": {
                gid: [{"id": rid, "name": rname} for rid, rname, _c in rlist]
                for gid, rlist in roles_map.items()
            },
        }
    )


@router.get("/automod/rules/{rule_id}", response_model=None)
async def api_automod_rules_get(
    rule_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Get a single automod rule."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        return JSONResponse({"error": "Not found"}, status_code=404)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    roles_map = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "rule": _serialize_rule(rule),
            "guilds": guilds_map,
            "channels": _channels_to_json(channels_map),
            "roles": {
                gid: [{"id": rid, "name": rname} for rid, rname, _c in rlist]
                for gid, rlist in roles_map.items()
            },
        }
    )


@router.post("/automod/rules", response_model=None)
async def api_automod_rules_create(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Create a new automod rule."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body = await request.json()
    guild_id = str(body.get("guild_id", "")).strip()
    if not guild_id:
        return JSONResponse({"error": "guild_id is required"}, status_code=400)

    fields, error = _validate_rule_body(body)
    if fields is None:
        return JSONResponse({"error": error}, status_code=400)

    async with get_resource_lock(f"automod:create:{guild_id}"):
        rule = AutoModRule(
            guild_id=guild_id,
            rule_type=fields["rule_type"],
            action=fields["action"],
            pattern=fields["pattern"],
            use_wildcard=fields["use_wildcard"],
            threshold_seconds=fields["threshold_seconds"],
            required_channel_id=fields["required_channel_id"],
            target_role_ids=fields["target_role_ids"],
            timeout_duration_seconds=fields["timeout_duration_seconds"],
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "rule": _serialize_rule(rule)}, status_code=201)


@router.put("/automod/rules/{rule_id}", response_model=None)
async def api_automod_rules_update(
    request: Request,
    rule_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update an automod rule."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body = await request.json()

    async with get_resource_lock(f"automod:edit:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            return JSONResponse({"error": "Not found"}, status_code=404)

        # For update, use existing rule_type if not provided
        if "rule_type" not in body:
            body["rule_type"] = rule.rule_type

        fields, error = _validate_rule_body(body)
        if fields is None:
            return JSONResponse({"error": error}, status_code=400)

        rule.action = fields["action"]
        rule.timeout_duration_seconds = fields["timeout_duration_seconds"]

        if rule.rule_type == "username_match":
            rule.pattern = fields["pattern"]
            rule.use_wildcard = fields["use_wildcard"]
        elif rule.rule_type in (
            "account_age",
            "role_acquired",
            "vc_join",
            "message_post",
        ):
            rule.threshold_seconds = fields["threshold_seconds"]
        elif rule.rule_type == "role_count":
            rule.threshold_seconds = fields["threshold_seconds"]
            rule.target_role_ids = fields["target_role_ids"]
        elif rule.rule_type in ("vc_without_intro", "msg_without_intro"):
            rule.required_channel_id = fields["required_channel_id"]

        await db.commit()
        await db.refresh(rule)

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "rule": _serialize_rule(rule)})


@router.delete("/automod/rules/{rule_id}", response_model=None)
async def api_automod_rules_delete(
    request: Request,
    rule_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete an automod rule."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"automod:delete:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(rule)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


@router.patch("/automod/rules/{rule_id}/toggle", response_model=None)
async def api_automod_rules_toggle(
    request: Request,
    rule_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Toggle an automod rule enabled/disabled."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"automod:toggle:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            return JSONResponse({"error": "Not found"}, status_code=404)

        rule.is_enabled = not rule.is_enabled
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True, "enabled": rule.is_enabled})


# ---------------------------------------------------------------------------
# Form data (for dropdown population)
# ---------------------------------------------------------------------------


@router.get("/automod/form-data", response_model=None)
async def api_automod_form_data(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Return guilds and channels for form dropdowns."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)
    roles_map = await _db._get_discord_roles_by_guild(db)

    return JSONResponse(
        {
            "guilds": guilds_map,
            "channels": _channels_to_json(channels_map),
            "roles": {
                gid: [{"id": rid, "name": rname} for rid, rname, _c in rlist]
                for gid, rlist in roles_map.items()
            },
        }
    )


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@router.get("/automod/logs", response_model=None)
async def api_automod_logs_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List automod logs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(AutoModLog).order_by(AutoModLog.created_at.desc()).limit(100)
    )
    logs = list(result.scalars().all())
    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "logs": [
                {
                    "id": log.id,
                    "guild_id": log.guild_id,
                    "user_id": log.user_id,
                    "username": log.username,
                    "action_taken": log.action_taken,
                    "reason": log.reason,
                    "rule_id": log.rule_id,
                    "created_at": (
                        log.created_at.isoformat() if log.created_at else None
                    ),
                }
                for log in logs
            ],
            "guilds": guilds_map,
        }
    )


# ---------------------------------------------------------------------------
# Ban logs
# ---------------------------------------------------------------------------


@router.get("/banlogs", response_model=None)
async def api_banlogs_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List ban logs."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(BanLog).order_by(BanLog.created_at.desc()).limit(100)
    )
    logs = list(result.scalars().all())
    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "logs": [
                {
                    "id": log.id,
                    "guild_id": log.guild_id,
                    "user_id": log.user_id,
                    "username": log.username,
                    "reason": log.reason,
                    "is_automod": log.is_automod,
                    "created_at": (
                        log.created_at.isoformat() if log.created_at else None
                    ),
                }
                for log in logs
            ],
            "guilds": guilds_map,
        }
    )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/automod/settings", response_model=None)
async def api_automod_settings_get(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Get automod settings (per-guild configs)."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(select(AutoModConfig))
    configs = list(result.scalars().all())

    configs_dict: dict[str, dict[str, Any]] = {}
    for c in configs:
        configs_dict[c.guild_id] = {
            "log_channel_id": c.log_channel_id,
            "intro_check_messages": c.intro_check_messages,
        }

    guilds_map, channels_map = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "configs": configs_dict,
            "guilds": guilds_map,
            "channels": _channels_to_json(channels_map),
        }
    )


@router.put("/automod/settings", response_model=None)
async def api_automod_settings_update(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Update automod settings for a guild."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body = await request.json()
    guild_id = str(body.get("guild_id", "")).strip()
    if not guild_id:
        return JSONResponse({"error": "guild_id is required"}, status_code=400)

    log_channel_id_raw = str(body.get("log_channel_id", "")).strip() or None
    intro_check_messages = max(0, min(int(body.get("intro_check_messages", 50)), 200))

    async with get_resource_lock(f"automod:settings:{guild_id}"):
        existing = await db.execute(
            select(AutoModConfig).where(AutoModConfig.guild_id == guild_id)
        )
        config = existing.scalar_one_or_none()

        if config:
            config.log_channel_id = log_channel_id_raw
            config.intro_check_messages = intro_check_messages
        else:
            config = AutoModConfig(
                guild_id=guild_id,
                log_channel_id=log_channel_id_raw,
                intro_check_messages=intro_check_messages,
            )
            db.add(config)

        await db.commit()
        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Ban list
# ---------------------------------------------------------------------------


@router.get("/automod/banlist", response_model=None)
async def api_automod_banlist_list(
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """List automod ban list entries."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await db.execute(
        select(AutoModBanList).order_by(
            AutoModBanList.guild_id, AutoModBanList.created_at.desc()
        )
    )
    entries = list(result.scalars().all())
    guilds_map, _ = await _db._get_discord_guilds_and_channels(db)

    return JSONResponse(
        {
            "entries": [
                {
                    "id": e.id,
                    "guild_id": e.guild_id,
                    "user_id": e.user_id,
                    "reason": e.reason,
                    "created_at": (e.created_at.isoformat() if e.created_at else None),
                }
                for e in entries
            ],
            "guilds": guilds_map,
        }
    )


@router.post("/automod/banlist", response_model=None)
async def api_automod_banlist_create(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Add an entry to the automod ban list."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    body = await request.json()
    guild_id = str(body.get("guild_id", "")).strip()
    user_id = str(body.get("user_id", "")).strip()
    reason_raw = str(body.get("reason", "")).strip() or None

    if not guild_id:
        return JSONResponse({"error": "guild_id is required"}, status_code=400)
    if not user_id or not user_id.isdigit():
        return JSONResponse(
            {"error": "user_id is required and must be numeric"}, status_code=400
        )

    async with get_resource_lock(f"automod:banlist:{guild_id}"):
        entry = AutoModBanList(
            guild_id=guild_id,
            user_id=user_id,
            reason=reason_raw,
        )
        db.add(entry)
        try:
            await db.commit()
            await db.refresh(entry)
        except Exception:
            await db.rollback()
            return JSONResponse({"error": "Duplicate entry"}, status_code=409)

        _security.record_form_submit(user_email, path)

    return JSONResponse(
        {
            "ok": True,
            "entry": {
                "id": entry.id,
                "guild_id": entry.guild_id,
                "user_id": entry.user_id,
                "reason": entry.reason,
                "created_at": (
                    entry.created_at.isoformat() if entry.created_at else None
                ),
            },
        },
        status_code=201,
    )


@router.delete("/automod/banlist/{entry_id}", response_model=None)
async def api_automod_banlist_delete(
    request: Request,
    entry_id: int,
    user: dict[str, Any] | None = Depends(get_current_user_jwt),
    db: AsyncSession = Depends(_db.get_db),
) -> JSONResponse:
    """Delete an entry from the automod ban list."""
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    user_email = user.get("sub", "")
    path = request.url.path

    if _security.is_form_cooldown_active(user_email, path):
        return JSONResponse({"error": "Too many requests"}, status_code=429)

    async with get_resource_lock(f"automod:banlist:delete:{entry_id}"):
        result = await db.execute(
            select(AutoModBanList).where(AutoModBanList.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return JSONResponse({"error": "Not found"}, status_code=404)

        await db.delete(entry)
        await db.commit()

        _security.record_form_submit(user_email, path)

    return JSONResponse({"ok": True})

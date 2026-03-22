"""AutoMod routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.web.app as _app
from src.database.models import (
    AutoModBanList,
    AutoModConfig,
    AutoModLog,
    AutoModRule,
    BanLog,
)
from src.utils import get_resource_lock
from src.web.templates import (
    automod_banlist_page,
    automod_create_page,
    automod_edit_page,
    automod_list_page,
    automod_logs_page,
    automod_settings_page,
    ban_logs_page,
)

router = APIRouter()


@router.get("/automod", response_model=None)
async def automod_list_view(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルール一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(AutoModRule).order_by(AutoModRule.guild_id, AutoModRule.created_at)
    )
    rules = list(result.scalars().all())
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=automod_list_page(
            rules,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.get("/automod/new", response_model=None)
async def automod_create_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルール作成フォーム。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=automod_create_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/automod/new", response_model=None)
async def automod_create_post(
    request: Request,
    guild_id: Annotated[str, Form()],
    rule_type: Annotated[str, Form()],
    action: Annotated[str, Form()] = "ban",
    pattern: Annotated[str, Form()] = "",
    use_wildcard: Annotated[str, Form()] = "",
    account_age_minutes: Annotated[str, Form()] = "",
    threshold_seconds: Annotated[str, Form()] = "",
    required_channel_id: Annotated[str, Form()] = "",
    timeout_duration_minutes: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルールを作成する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod/new", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/automod", status_code=302)

    # Validate rule_type
    valid_rule_types = (
        "username_match",
        "account_age",
        "no_avatar",
        "role_acquired",
        "vc_join",
        "message_post",
        "vc_without_intro",
        "msg_without_intro",
    )
    if rule_type not in valid_rule_types:
        return RedirectResponse(url="/automod/new", status_code=302)

    # Validate action
    if action not in ("ban", "kick", "timeout"):
        return RedirectResponse(url="/automod/new", status_code=302)

    # Validate timeout_duration_minutes
    MAX_TIMEOUT_MINUTES = 40320
    timeout_duration_seconds: int | None = None
    if action == "timeout":
        try:
            timeout_minutes_int = int(timeout_duration_minutes)
        except (ValueError, TypeError):
            return RedirectResponse(url="/automod/new", status_code=302)
        if timeout_minutes_int < 1 or timeout_minutes_int > MAX_TIMEOUT_MINUTES:
            return RedirectResponse(url="/automod/new", status_code=302)
        timeout_duration_seconds = timeout_minutes_int * 60

    # Validate fields based on rule_type
    if rule_type == "username_match" and not pattern.strip():
        return RedirectResponse(url="/automod/new", status_code=302)

    threshold_seconds_int: int | None = None
    if rule_type == "account_age":
        try:
            minutes_int = int(account_age_minutes)
        except (ValueError, TypeError):
            return RedirectResponse(url="/automod/new", status_code=302)
        if minutes_int < 1 or minutes_int > 20160:
            return RedirectResponse(url="/automod/new", status_code=302)
        threshold_seconds_int = minutes_int * 60

    if rule_type in ("role_acquired", "vc_join", "message_post"):
        try:
            threshold_seconds_int = int(threshold_seconds)
        except (ValueError, TypeError):
            return RedirectResponse(url="/automod/new", status_code=302)
        if threshold_seconds_int < 1 or threshold_seconds_int > 3600:
            return RedirectResponse(url="/automod/new", status_code=302)

    required_channel_id_str: str | None = None
    if rule_type in ("vc_without_intro", "msg_without_intro"):
        if not required_channel_id.strip():
            return RedirectResponse(url="/automod/new", status_code=302)
        if not required_channel_id.strip().isdigit():
            return RedirectResponse(url="/automod/new", status_code=302)
        required_channel_id_str = required_channel_id.strip()

    async with get_resource_lock(f"automod:create:{guild_id}"):
        rule = AutoModRule(
            guild_id=guild_id,
            rule_type=rule_type,
            action=action,
            pattern=pattern.strip() if rule_type == "username_match" else None,
            use_wildcard=bool(use_wildcard) if rule_type == "username_match" else False,
            threshold_seconds=threshold_seconds_int,
            required_channel_id=required_channel_id_str,
            timeout_duration_seconds=timeout_duration_seconds,
        )
        db.add(rule)
        await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod", status_code=302)


@router.get("/automod/{rule_id}/edit", response_model=None)
async def automod_edit_get(
    rule_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルール編集フォーム。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        return RedirectResponse(url="/automod", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=automod_edit_page(
            rule=rule,
            guilds_map=guilds_map,
            channels_map=channels_map,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/automod/{rule_id}/edit", response_model=None)
async def automod_edit_post(
    request: Request,
    rule_id: int,
    action: Annotated[str, Form()] = "ban",
    pattern: Annotated[str, Form()] = "",
    use_wildcard: Annotated[str, Form()] = "",
    account_age_minutes: Annotated[str, Form()] = "",
    threshold_seconds: Annotated[str, Form()] = "",
    required_channel_id: Annotated[str, Form()] = "",
    timeout_duration_minutes: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルールを更新する。"""
    edit_url = f"/automod/{rule_id}/edit"
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url=edit_url, status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url=edit_url, status_code=302)

    if action not in ("ban", "kick", "timeout"):
        return RedirectResponse(url=edit_url, status_code=302)

    async with get_resource_lock(f"automod:edit:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            return RedirectResponse(url="/automod", status_code=302)

        rule.action = action

        # Handle timeout_duration_seconds
        MAX_TIMEOUT_MINUTES = 40320
        if action == "timeout":
            try:
                timeout_minutes_int = int(timeout_duration_minutes)
            except (ValueError, TypeError):
                return RedirectResponse(url=edit_url, status_code=302)
            if timeout_minutes_int < 1 or timeout_minutes_int > MAX_TIMEOUT_MINUTES:
                return RedirectResponse(url=edit_url, status_code=302)
            rule.timeout_duration_seconds = timeout_minutes_int * 60
        else:
            rule.timeout_duration_seconds = None

        if rule.rule_type == "username_match":
            if not pattern.strip():
                return RedirectResponse(url=edit_url, status_code=302)
            rule.pattern = pattern.strip()
            rule.use_wildcard = bool(use_wildcard)

        elif rule.rule_type == "account_age":
            try:
                minutes_int = int(account_age_minutes)
            except (ValueError, TypeError):
                return RedirectResponse(url=edit_url, status_code=302)
            if minutes_int < 1 or minutes_int > 20160:
                return RedirectResponse(url=edit_url, status_code=302)
            rule.threshold_seconds = minutes_int * 60

        elif rule.rule_type in ("role_acquired", "vc_join", "message_post"):
            try:
                seconds_int = int(threshold_seconds)
            except (ValueError, TypeError):
                return RedirectResponse(url=edit_url, status_code=302)
            if seconds_int < 1 or seconds_int > 3600:
                return RedirectResponse(url=edit_url, status_code=302)
            rule.threshold_seconds = seconds_int

        elif rule.rule_type in ("vc_without_intro", "msg_without_intro"):
            if not required_channel_id.strip():
                return RedirectResponse(url=edit_url, status_code=302)
            if not required_channel_id.strip().isdigit():
                return RedirectResponse(url=edit_url, status_code=302)
            rule.required_channel_id = required_channel_id.strip()

        await db.commit()
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod", status_code=302)


@router.post("/automod/{rule_id}/delete", response_model=None)
async def automod_delete(
    request: Request,
    rule_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルールを削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/automod", status_code=302)

    async with get_resource_lock(f"automod:delete:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule:
            await db.delete(rule)
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod", status_code=302)


@router.post("/automod/{rule_id}/toggle", response_model=None)
async def automod_toggle(
    request: Request,
    rule_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ルールの有効/無効を切り替える。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/automod", status_code=302)

    async with get_resource_lock(f"automod:toggle:{rule_id}"):
        result = await db.execute(select(AutoModRule).where(AutoModRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule:
            rule.is_enabled = not rule.is_enabled
            await db.commit()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod", status_code=302)


@router.get("/automod/logs", response_model=None)
async def automod_logs_view(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod ログ一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(AutoModLog).order_by(AutoModLog.created_at.desc()).limit(100)
    )
    logs = list(result.scalars().all())
    guilds_map, _ = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=automod_logs_page(
            logs,
            guilds_map=guilds_map,
        )
    )


@router.get("/banlogs", response_model=None)
async def ban_logs_view(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """BAN ログ一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(BanLog).order_by(BanLog.created_at.desc()).limit(100)
    )
    logs = list(result.scalars().all())
    guilds_map, _ = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=ban_logs_page(
            logs,
            guilds_map=guilds_map,
        )
    )


@router.get("/automod/settings", response_model=None)
async def automod_settings_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod 設定ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    # 既存の設定を取得
    result = await db.execute(select(AutoModConfig))
    configs = list(result.scalars().all())
    configs_map = {c.guild_id: c.log_channel_id for c in configs}
    intro_check_map = {c.guild_id: c.intro_check_messages for c in configs}

    return HTMLResponse(
        content=automod_settings_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            configs_map=configs_map,
            intro_check_map=intro_check_map,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/automod/settings", response_model=None)
async def automod_settings_post(
    request: Request,
    guild_id: Annotated[str, Form()],
    log_channel_id: Annotated[str, Form()] = "",
    intro_check_messages: Annotated[int, Form()] = 50,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod 設定を保存する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod/settings", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/automod/settings", status_code=302)

    if not guild_id:
        return RedirectResponse(url="/automod/settings", status_code=302)

    intro_check_messages = max(0, min(intro_check_messages, 200))

    async with get_resource_lock(f"automod:settings:{guild_id}"):
        existing = await db.execute(
            select(AutoModConfig).where(AutoModConfig.guild_id == guild_id)
        )
        config = existing.scalar_one_or_none()

        channel_value = log_channel_id.strip() if log_channel_id.strip() else None

        if config:
            config.log_channel_id = channel_value
            config.intro_check_messages = intro_check_messages
        else:
            config = AutoModConfig(
                guild_id=guild_id,
                log_channel_id=channel_value,
                intro_check_messages=intro_check_messages,
            )
            db.add(config)

        await db.commit()
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod/settings", status_code=302)


@router.get("/automod/banlist", response_model=None)
async def automod_banlist_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """AutoMod BANリスト一覧ページ。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(AutoModBanList).order_by(
            AutoModBanList.guild_id,
            AutoModBanList.created_at.desc(),
        )
    )
    entries = list(result.scalars().all())
    guilds_map, _ = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=automod_banlist_page(
            entries,
            guilds_map=guilds_map,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/automod/banlist", response_model=None)
async def automod_banlist_post(
    request: Request,
    guild_id: Annotated[str, Form()],
    user_id: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """BANリストにユーザーIDを追加する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod/banlist", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/automod/banlist", status_code=302)

    user_id = user_id.strip()
    if not user_id or not user_id.isdigit():
        return RedirectResponse(url="/automod/banlist", status_code=302)

    if not guild_id:
        return RedirectResponse(url="/automod/banlist", status_code=302)

    reason_value = reason.strip() if reason.strip() else None

    async with get_resource_lock(f"automod:banlist:{guild_id}"):
        entry = AutoModBanList(
            guild_id=guild_id,
            user_id=user_id,
            reason=reason_value,
        )
        db.add(entry)
        try:
            await db.commit()
        except Exception:
            await db.rollback()

        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/automod/banlist", status_code=302)


@router.post("/automod/banlist/{entry_id}/delete", response_model=None)
async def automod_banlist_delete(
    entry_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """BANリストからエントリを削除する。"""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/automod/banlist", status_code=302)

    result = await db.execute(
        select(AutoModBanList).where(AutoModBanList.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry:
        await db.delete(entry)
        await db.commit()

    return RedirectResponse(url="/automod/banlist", status_code=302)

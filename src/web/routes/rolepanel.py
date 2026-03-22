"""Role panel routes."""

from contextlib import suppress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.web.app as _app
from src.database.models import RolePanel, RolePanelItem
from src.utils import get_resource_lock, is_valid_emoji, normalize_emoji
from src.web.templates import (
    role_panel_create_page,
    role_panel_detail_page,
    role_panels_list_page,
)

router = APIRouter()


@router.get("/rolepanels", response_model=None)
async def rolepanels_list(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """List all role panels."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # パネル一覧を取得 (アイテムも一緒に取得)
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .order_by(RolePanel.created_at.desc())
    )
    panels = list(result.scalars().all())

    # パネルID -> アイテムリストのマップを作成
    items_by_panel: dict[int, list[RolePanelItem]] = {}
    for panel in panels:
        items_by_panel[panel.id] = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名のルックアップを取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)

    return HTMLResponse(
        content=role_panels_list_page(
            panels,
            items_by_panel,
            csrf_token=_app.generate_csrf_token(),
            guilds_map=guilds_map,
            channels_map=channels_map,
        )
    )


@router.post("/rolepanels/{panel_id}/delete", response_model=None)
async def rolepanel_delete(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url="/rolepanels", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/rolepanels", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"rolepanel:delete:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if panel:
            # Discord に投稿済みの場合はメッセージも削除
            if panel.message_id:
                await _app.delete_discord_message(panel.channel_id, panel.message_id)

            await db.delete(panel)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url="/rolepanels", status_code=302)


@router.post("/rolepanels/{panel_id}/copy", response_model=None)
async def rolepanel_copy(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Duplicate a role panel with all its items."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url="/rolepanels", status_code=302)

    # 元のパネルとアイテムを取得
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    async with get_resource_lock(f"rolepanel:copy:{panel_id}"):
        # 新しいパネルを作成 (message_id なし = 未投稿)
        new_panel = RolePanel(
            guild_id=panel.guild_id,
            channel_id=panel.channel_id,
            panel_type=panel.panel_type,
            title=f"{panel.title} (Copy)",
            description=panel.description,
            color=panel.color,
            use_embed=panel.use_embed,
            remove_reaction=panel.remove_reaction,
        )
        db.add(new_panel)
        await db.flush()

        # アイテムをコピー
        for item in sorted(panel.items, key=lambda x: x.position):
            new_item = RolePanelItem(
                panel_id=new_panel.id,
                role_id=item.role_id,
                emoji=item.emoji,
                label=item.label,
                style=item.style,
                position=item.position,
            )
            db.add(new_item)

        await db.commit()
        await db.refresh(new_panel)

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    # コピーしたパネルの詳細ページにリダイレクト
    return RedirectResponse(
        url=f"/rolepanels/{new_panel.id}?success=Panel+duplicated",
        status_code=302,
    )


@router.post("/rolepanels/{panel_id}/toggle-remove-reaction", response_model=None)
async def rolepanel_toggle_remove_reaction(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Toggle the remove_reaction flag for a role panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    # 二重ロック: 同じリソースへの同時操作を防止
    async with get_resource_lock(f"rolepanel:toggle:{panel_id}"):
        result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
        panel = result.scalar_one_or_none()
        if panel and panel.panel_type == "reaction":
            panel.remove_reaction = not panel.remove_reaction
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)


@router.get("/rolepanels/new", response_model=None)
async def rolepanel_create_get(
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show role panel create form."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    discord_roles = await _app._get_discord_roles_by_guild(db)
    return HTMLResponse(
        content=role_panel_create_page(
            guilds_map=guilds_map,
            channels_map=channels_map,
            discord_roles=discord_roles,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/rolepanels/new", response_model=None)
async def rolepanel_create_post(
    request: Request,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    guild_id: Annotated[str, Form()] = "",
    channel_id: Annotated[str, Form()] = "",
    panel_type: Annotated[str, Form()] = "button",
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    use_embed: Annotated[str, Form()] = "1",
    color: Annotated[str, Form()] = "",
    remove_reaction: Annotated[str, Form()] = "",
    action: Annotated[str, Form()] = "create",
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Create a new role panel with role items."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # エラー時にも選択肢を表示するためにギルド/チャンネル/ロール情報を取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    discord_roles = await _app._get_discord_roles_by_guild(db)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=role_panel_create_page(
                error="Invalid security token. Please try again.",
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return HTMLResponse(
            content=role_panel_create_page(
                error="Please wait before submitting again.",
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=429,
        )

    # Trim input values
    guild_id = guild_id.strip()
    channel_id = channel_id.strip()
    panel_type = panel_type.strip()
    title = title.strip()
    description = description.strip()

    # Convert use_embed to boolean
    use_embed_bool = use_embed == "1"

    # Convert color to integer (hex string -> int)
    color_int: int | None = None
    color = color.strip()
    if color and use_embed_bool:
        # Remove # prefix if present
        color_hex = color.lstrip("#")
        if len(color_hex) == 6:
            with suppress(ValueError):
                color_int = int(color_hex, 16)

    # Convert remove_reaction to boolean (only effective for reaction panels)
    remove_reaction_bool = remove_reaction == "1" and panel_type == "reaction"

    # Parse role items from form data (バリデーションエラー時に保持するため先に解析)
    form_data = await request.form()
    item_emojis = form_data.getlist("item_emoji[]")
    item_role_ids = form_data.getlist("item_role_id[]")
    item_labels = form_data.getlist("item_label[]")
    item_styles = form_data.getlist("item_style[]")
    item_positions = form_data.getlist("item_position[]")

    # フォームから送信されたアイテムを保持用に収集
    submitted_items: list[dict[str, str | int | None]] = []
    for i in range(len(item_emojis)):
        submitted_items.append(
            {
                "emoji": str(item_emojis[i]).strip() if i < len(item_emojis) else "",
                "role_id": str(item_role_ids[i]).strip()
                if i < len(item_role_ids)
                else "",
                "label": str(item_labels[i]).strip() if i < len(item_labels) else "",
                "style": str(item_styles[i]).strip()
                if i < len(item_styles)
                else "secondary",
                "position": i,
            }
        )

    # Validation helper
    def error_response(error: str) -> HTMLResponse:
        return HTMLResponse(
            content=role_panel_create_page(
                error=error,
                guild_id=guild_id,
                channel_id=channel_id,
                panel_type=panel_type,
                title=title,
                description=description,
                use_embed=use_embed_bool,
                color=color,
                remove_reaction=remove_reaction_bool,
                guilds_map=guilds_map,
                channels_map=channels_map,
                discord_roles=discord_roles,
                csrf_token=_app.generate_csrf_token(),
                existing_items=submitted_items,
            )
        )

    # Validation
    if not guild_id:
        return error_response("Guild ID is required")

    if not guild_id.isdigit():
        return error_response("Guild ID must be a number")

    if not channel_id:
        return error_response("Channel ID is required")

    if not channel_id.isdigit():
        return error_response("Channel ID must be a number")

    if panel_type not in ("button", "reaction"):
        return error_response("Invalid panel type")

    if not title:
        return error_response("Title is required")

    if len(title) > 256:
        return error_response("Title must be 256 characters or less")

    if len(description) > 4096:
        return error_response("Description must be 4096 characters or less")

    # Validate at least one role item (only for "create" action)
    is_draft = action == "save_draft"
    if not is_draft and not item_emojis:
        return error_response("At least one role item is required")

    # Validate and collect role items
    role_items_data: list[dict[str, str | int | None]] = []
    seen_emojis: set[str] = set()

    # Pad item_styles to match the length of other lists
    while len(item_styles) < len(item_emojis):
        item_styles.append("secondary")

    valid_styles = {"primary", "secondary", "success", "danger"}

    items_zip = zip(
        item_emojis,
        item_role_ids,
        item_labels,
        item_styles,
        item_positions,
        strict=False,
    )
    for i, (emoji, role_id, label, style, position) in enumerate(items_zip):
        # Trim values
        emoji = str(emoji).strip()
        role_id = str(role_id).strip()
        label = str(label).strip()
        style = str(style).strip()
        position_str = str(position).strip()

        # Validate emoji
        if not emoji:
            return error_response(f"Role item {i + 1}: Emoji is required")
        if len(emoji) > 64:
            return error_response(f"Role item {i + 1}: Emoji must be 64 chars or less")
        if not is_valid_emoji(emoji):
            return error_response(
                f"Role item {i + 1}: Invalid emoji. Use a Unicode emoji (\U0001f3ae) "
                "or Discord custom emoji (<:name:id>)"
            )
        if emoji in seen_emojis:
            return error_response(f"Role item {i + 1}: Duplicate emoji '{emoji}'")
        seen_emojis.add(emoji)

        # Validate role_id
        if not role_id:
            return error_response(f"Role item {i + 1}: Role ID is required")
        if not role_id.isdigit():
            return error_response(f"Role item {i + 1}: Role ID must be a number")

        # Validate label
        if label and len(label) > 80:
            return error_response(f"Role item {i + 1}: Label must be 80 chars or less")

        # Validate style
        if style not in valid_styles:
            style = "secondary"

        # Parse position
        try:
            pos = int(position_str) if position_str else i
        except ValueError:
            pos = i

        role_items_data.append(
            {
                "emoji": emoji,
                "role_id": role_id,
                "label": label if label else None,
                "style": style,
                "position": pos,
            }
        )

    # 二重ロック: 同じユーザーによる同時パネル作成を防止
    async with get_resource_lock(f"rolepanel:create:{user_email}"):
        # Create the role panel
        panel = RolePanel(
            guild_id=guild_id,
            channel_id=channel_id,
            panel_type=panel_type,
            title=title,
            description=description if description else None,
            color=color_int,
            use_embed=use_embed_bool,
            remove_reaction=remove_reaction_bool,
        )
        db.add(panel)
        await db.flush()  # Get the panel ID without committing

        # Create role items
        for item_data in role_items_data:
            item = RolePanelItem(
                panel_id=panel.id,
                role_id=str(item_data["role_id"]),
                emoji=normalize_emoji(str(item_data["emoji"])),
                label=item_data["label"] if item_data["label"] else None,
                style=str(item_data.get("style") or "secondary"),
                position=int(item_data["position"]) if item_data["position"] else 0,
            )
            db.add(item)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            # UniqueConstraint 違反 (panel_id, emoji) の場合
            if "uq_panel_emoji" in str(e.orig):
                return error_response("Duplicate emoji in role items")
            raise

        await db.refresh(panel)

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    # 作成後は詳細ページにリダイレクト
    return RedirectResponse(url=f"/rolepanels/{panel.id}", status_code=302)


@router.get("/rolepanels/{panel_id}", response_model=None)
async def rolepanel_detail(
    panel_id: int,
    success: str | None = None,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Show role panel detail page."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    items = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名を取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    guild_name = guilds_map.get(panel.guild_id)
    # チャンネル名を取得
    guild_channels = channels_map.get(panel.guild_id, [])
    channel_name = next(
        (name for cid, name in guild_channels if cid == panel.channel_id), None
    )

    # このギルドのDiscordロール情報を取得
    discord_roles = await _app._get_discord_roles_by_guild(db)
    guild_discord_roles = discord_roles.get(panel.guild_id, [])

    return HTMLResponse(
        content=role_panel_detail_page(
            panel,
            items,
            success=success,
            discord_roles=guild_discord_roles,
            guild_name=guild_name,
            channel_name=channel_name,
            csrf_token=_app.generate_csrf_token(),
        )
    )


@router.post("/rolepanels/{panel_id}/edit", response_model=None)
async def rolepanel_edit(
    request: Request,
    panel_id: int,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    color: Annotated[str, Form()] = "",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Edit role panel title, description, and color."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    # クールタイムチェック
    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Please+wait+before+editing+again",
            status_code=302,
        )

    # バリデーション
    title = title.strip()
    if not title:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Title+is+required",
            status_code=302,
        )
    if len(title) > 100:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Title+must+be+100+characters+or+less",
            status_code=302,
        )

    description = description.strip()
    if len(description) > 2000:
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Description+must+be+2000+characters+or+less",
            status_code=302,
        )

    # パネルを取得して更新
    result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    panel.title = title
    panel.description = description if description else None

    # Update color if panel uses embed
    if panel.use_embed:
        color = color.strip()
        color_hex = color.lstrip("#")
        if len(color_hex) == 6:
            with suppress(ValueError):
                panel.color = int(color_hex, 16)

    await db.commit()

    # クールタイム記録
    _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Panel+updated",
        status_code=302,
    )


@router.post("/rolepanels/{panel_id}/post", response_model=None)
async def rolepanel_post_to_discord(
    request: Request,
    panel_id: int,
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Post role panel to Discord channel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Invalid+security+token",
            status_code=302,
        )

    # クールタイムチェック
    user_email = user.get("email", "")
    path = str(request.url.path)
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Please+wait+before+posting+again",
            status_code=302,
        )

    # パネルを取得
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    items = sorted(panel.items, key=lambda x: x.position)

    # 既存メッセージがある場合は編集、なければ新規投稿
    if panel.message_id:
        # 既存メッセージを編集
        success, error_msg = await _app.edit_role_panel_in_discord(panel, items)
        message_id = panel.message_id if success else None
        action_text = "Updated"
    else:
        # 新規投稿
        success, message_id, error_msg = await _app.post_role_panel_to_discord(
            panel, items
        )
        action_text = "Posted"

    if not success:
        error_encoded = (error_msg or "Unknown error").replace(" ", "+")
        return RedirectResponse(
            url=f"/rolepanels/{panel_id}?success=Failed:+{error_encoded}",
            status_code=302,
        )

    # 新規投稿の場合はメッセージ ID を保存
    if message_id and message_id != panel.message_id:
        panel.message_id = message_id
        await db.commit()

    # リアクション式の場合はリアクションを追加/更新
    target_message_id = message_id or panel.message_id
    if panel.panel_type == "reaction" and items and target_message_id:
        # 編集時は既存リアクションをクリア
        is_edit = action_text == "Updated"
        react_success, react_error = await _app.add_reactions_to_message(
            panel.channel_id,
            target_message_id,
            items,
            clear_existing=is_edit,
        )
        if not react_success:
            return RedirectResponse(
                url=f"/rolepanels/{panel_id}?success={action_text}+but+reactions+failed:+{react_error}",
                status_code=302,
            )

    # クールタイム記録
    _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success={action_text}+to+Discord",
        status_code=302,
    )


@router.post("/rolepanels/{panel_id}/items/add", response_model=None)
async def rolepanel_add_item(
    request: Request,
    panel_id: int,
    emoji: Annotated[str, Form()] = "",
    role_id: Annotated[str, Form()] = "",
    label: Annotated[str, Form()] = "",
    style: Annotated[str, Form()] = "secondary",
    csrf_token: Annotated[str, Form()] = "",
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Add a role item to a panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Get the panel
    result = await db.execute(
        select(RolePanel)
        .options(selectinload(RolePanel.items))
        .where(RolePanel.id == panel_id)
    )
    panel = result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    # Trim inputs
    emoji = emoji.strip()
    role_id = role_id.strip()
    label = label.strip()

    items = sorted(panel.items, key=lambda x: x.position)

    # ギルド・チャンネル名を取得
    guilds_map, channels_map = await _app._get_discord_guilds_and_channels(db)
    guild_name = guilds_map.get(panel.guild_id)
    guild_channels = channels_map.get(panel.guild_id, [])
    channel_name = next(
        (name for cid, name in guild_channels if cid == panel.channel_id), None
    )

    # このギルドのDiscordロール情報を取得
    discord_roles = await _app._get_discord_roles_by_guild(db)
    guild_discord_roles = discord_roles.get(panel.guild_id, [])

    # Validation helper
    def error_response(error: str) -> HTMLResponse:
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error=error,
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=_app.generate_csrf_token(),
            )
        )

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error="Invalid security token. Please try again.",
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=403,
        )

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return HTMLResponse(
            content=role_panel_detail_page(
                panel,
                items,
                error="Please wait before submitting again.",
                discord_roles=guild_discord_roles,
                guild_name=guild_name,
                channel_name=channel_name,
                csrf_token=_app.generate_csrf_token(),
            ),
            status_code=429,
        )

    # Validation
    if not emoji:
        return error_response("Emoji is required")

    if len(emoji) > 64:
        return error_response("Emoji must be 64 characters or less")

    if not is_valid_emoji(emoji):
        return error_response(
            "Invalid emoji. Use a Unicode emoji (\U0001f3ae) "
            "or Discord custom emoji (<:name:id>)"
        )

    if not role_id:
        return error_response("Role ID is required")

    if not role_id.isdigit():
        return error_response("Role ID must be a number")

    if label and len(label) > 80:
        return error_response("Label must be 80 characters or less")

    # Check for duplicate emoji
    # Normalize emoji for consistent comparison and storage
    normalized_emoji = normalize_emoji(emoji)

    for item in items:
        if item.emoji == normalized_emoji:
            return error_response(f"Emoji '{emoji}' is already used in this panel")

    # Validate style
    valid_styles = {"primary", "secondary", "success", "danger"}
    if style not in valid_styles:
        style = "secondary"

    # Auto-calculate position from existing items
    next_position = max((it.position for it in items), default=-1) + 1

    # 二重ロック: 同じパネルへの同時アイテム追加を防止
    async with get_resource_lock(f"rolepanel:add_item:{panel_id}"):
        # Create the item
        item = RolePanelItem(
            panel_id=panel_id,
            role_id=role_id,
            emoji=normalized_emoji,
            label=label if label else None,
            style=style,
            position=next_position,
        )
        db.add(item)

        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            if "uq_panel_emoji" in str(e.orig):
                return error_response(f"Emoji '{emoji}' is already used in this panel")
            raise

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Role+item+added", status_code=302
    )


@router.post("/rolepanels/{panel_id}/items/{item_id}/delete", response_model=None)
async def rolepanel_delete_item(
    request: Request,
    panel_id: int,
    item_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    csrf_token: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Delete a role item from a panel."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # CSRF トークン検証
    if not _app.validate_csrf_token(csrf_token):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    user_email = user.get("email", "")
    path = request.url.path

    # クールタイムチェック
    if _app.is_form_cooldown_active(user_email, path):
        return RedirectResponse(url=f"/rolepanels/{panel_id}", status_code=302)

    # Check panel exists
    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = panel_result.scalar_one_or_none()
    if not panel:
        return RedirectResponse(url="/rolepanels", status_code=302)

    # 二重ロック: 同じアイテムへの同時削除を防止
    async with get_resource_lock(f"rolepanel:delete_item:{panel_id}:{item_id}"):
        # Get and delete the item
        result = await db.execute(
            select(RolePanelItem).where(
                RolePanelItem.id == item_id, RolePanelItem.panel_id == panel_id
            )
        )
        item = result.scalar_one_or_none()
        if item:
            await db.delete(item)
            await db.commit()

        # クールタイム記録
        _app.record_form_submit(user_email, path)

    return RedirectResponse(
        url=f"/rolepanels/{panel_id}?success=Role+item+deleted", status_code=302
    )


@router.post("/rolepanels/{panel_id}/items/reorder", response_model=None)
async def rolepanel_reorder_items(
    request: Request,
    panel_id: int,
    user: dict[str, Any] | None = Depends(_app.get_current_user),
    db: AsyncSession = Depends(_app.get_db),
) -> Response:
    """Reorder role items via drag-and-drop."""
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    csrf_token = body.get("csrf_token", "")
    if not _app.validate_csrf_token(csrf_token):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    item_ids = body.get("item_ids", [])
    if not isinstance(item_ids, list):
        return JSONResponse({"error": "Invalid item_ids"}, status_code=400)

    # Check panel exists
    panel_result = await db.execute(select(RolePanel).where(RolePanel.id == panel_id))
    panel = panel_result.scalar_one_or_none()
    if not panel:
        return JSONResponse({"error": "Panel not found"}, status_code=404)

    async with get_resource_lock(f"rolepanel:reorder:{panel_id}"):
        for position, item_id in enumerate(item_ids):
            await db.execute(
                update(RolePanelItem)
                .where(
                    RolePanelItem.id == int(item_id),
                    RolePanelItem.panel_id == panel_id,
                )
                .values(position=position)
            )
        await db.commit()

    return JSONResponse({"ok": True})

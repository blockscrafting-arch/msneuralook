"""Inline keyboards for admin panel."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Callback prefixes (max 64 bytes per callback_data)
ADMIN_MAIN = "admin_main"
ADMIN_SRC = "admin_src"
ADMIN_SRC_ADD = "admin_src_add"
ADMIN_SRC_DEL = "admin_src_del"  # + _id
ADMIN_TGT = "admin_tgt"
ADMIN_TGT_EDIT = "admin_tgt_edit"
ADMIN_ED = "admin_ed"
ADMIN_ED_ADD = "admin_ed_add"
ADMIN_ED_DEL = "admin_ed_del"  # + _user_id
ADMIN_ADM = "admin_adm"
ADMIN_ADM_ADD = "admin_adm_add"
ADMIN_ADM_DEL = "admin_adm_del"  # + _user_id
ADMIN_KW = "admin_kw"
ADMIN_KW_ADD = "admin_kw_add"
ADMIN_KW_DEL = "admin_kw_del"  # + _id
ADMIN_TGT_ADD = "admin_tgt_add"
ADMIN_TGT_DEL = "admin_tgt_del"  # + _id
ADMIN_BACK = "admin_back"
ADMIN_CLOSE = "admin_close"
ADMIN_PROMPT = "admin_prompt"
ADMIN_PROMPT_EDIT = "admin_prompt_edit"
ADMIN_PROMPT_SHOW_FULL = "admin_prompt_full"
ADMIN_PROMPT_RESET = "admin_prompt_reset"
ADMIN_KG = "admin_kg"
ADMIN_KG_ADD = "admin_kg_add"
ADMIN_KG_DEL = "admin_kg_del"  # + _id
ADMIN_KG_OPEN = "admin_kg_open"  # + _id
ADMIN_KG_ADD_KW = "admin_kg_ak"  # + _id  (add keyword to group)
ADMIN_KG_BULK = "admin_kg_bulk"  # + _id  (add list to this group)
ADMIN_KG_SHOW_ALL = "admin_kg_showall"  # + _id  (show all as list)
ADMIN_KG_CLEAR = "admin_kg_clear"  # + _id  (remove all keywords from group)
ADMIN_KW_BULK = "admin_kw_bulk"
ADMIN_SCHED = "admin_sched"
ADMIN_SCHED_REFRESH = "admin_sched_refresh"
ADMIN_SCHED_EDIT = "admin_sched_edit"
ADMIN_SCHED_CANCEL = "admin_sched_cancel"


def editor_admin_keyboard() -> InlineKeyboardMarkup:
    """Limited admin menu for editors: no Редакторы, no Админы."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каналы-источники", callback_data=ADMIN_SRC)],
        [InlineKeyboardButton(text="Целевые каналы", callback_data=ADMIN_TGT)],
        [InlineKeyboardButton(text="Группы маркеров", callback_data=ADMIN_KG)],
        [InlineKeyboardButton(text="Слова-маркеры", callback_data=ADMIN_KW)],
        [InlineKeyboardButton(text="Отложенные посты", callback_data=ADMIN_SCHED)],
        [InlineKeyboardButton(text="Промпт OpenAI", callback_data=ADMIN_PROMPT)],
        [InlineKeyboardButton(text="Закрыть", callback_data=ADMIN_CLOSE)],
    ])


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Main admin menu: sources, target channels, keyword groups, keywords, editors, admins, schedule, prompt, close."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каналы-источники", callback_data=ADMIN_SRC)],
        [InlineKeyboardButton(text="Целевые каналы", callback_data=ADMIN_TGT)],
        [InlineKeyboardButton(text="Группы маркеров", callback_data=ADMIN_KG)],
        [InlineKeyboardButton(text="Слова-маркеры", callback_data=ADMIN_KW)],
        [InlineKeyboardButton(text="Отложенные посты", callback_data=ADMIN_SCHED)],
        [InlineKeyboardButton(text="Редакторы", callback_data=ADMIN_ED)],
        [InlineKeyboardButton(text="Админы", callback_data=ADMIN_ADM)],
        [InlineKeyboardButton(text="Промпт OpenAI", callback_data=ADMIN_PROMPT)],
        [InlineKeyboardButton(text="Закрыть", callback_data=ADMIN_CLOSE)],
    ])


def admin_prompt_keyboard(back: bool = True, show_full: bool = True) -> InlineKeyboardMarkup:
    """Prompt submenu: Edit, Show full, Reset to default, Back."""
    rows = [
        [InlineKeyboardButton(text="Изменить промпт", callback_data=ADMIN_PROMPT_EDIT)],
    ]
    if show_full:
        rows.append([InlineKeyboardButton(text="Показать полностью", callback_data=ADMIN_PROMPT_SHOW_FULL)])
    rows.append([InlineKeyboardButton(text="Сброс к дефолту", callback_data=ADMIN_PROMPT_RESET)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_prompt_full_keyboard() -> InlineKeyboardMarkup:
    """Keyboard when showing full prompt: only Back to prompt menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data=ADMIN_PROMPT)],
    ])


def admin_back_keyboard(to_main: bool = True) -> InlineKeyboardMarkup:
    """Single 'Назад' button. to_main=True -> admin_main, else just back."""
    data = ADMIN_MAIN if to_main else ADMIN_BACK
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data=data)],
    ])


def admin_sources_keyboard(
    channels: list[dict],
    back: bool = True,
) -> InlineKeyboardMarkup:
    """Sources submenu: list of channels with delete button + Add + Back."""
    rows = []
    for ch in channels:
        ident = ch.get("channel_identifier", "")
        display = ch.get("display_name") or ident
        cid = ch.get("id")
        if cid is not None:
            label = (display[:28] + "…") if len(display) > 28 else display
            rows.append([
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"{ADMIN_SRC_DEL}_{cid}",
                ),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data=ADMIN_SRC_ADD)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_target_keyboard(back: bool = True) -> InlineKeyboardMarkup:
    """Target channel submenu: Change + Back (legacy single target)."""
    rows = [
        [InlineKeyboardButton(text="Изменить целевой канал", callback_data=ADMIN_TGT_EDIT)],
    ]
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_target_channels_keyboard(
    channels: list[dict],
    back: bool = True,
) -> InlineKeyboardMarkup:
    """Target channels submenu: list with delete + Add + Back."""
    rows = []
    for ch in channels:
        ident = ch.get("channel_identifier", "")
        display = ch.get("display_name") or ident
        cid = ch.get("id")
        if cid is not None:
            label = (display[:28] + "…") if len(str(display)) > 28 else display
            rows.append([
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"{ADMIN_TGT_DEL}_{cid}",
                ),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data=ADMIN_TGT_ADD)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keywords_keyboard(
    keywords: list[dict],
    back: bool = True,
) -> InlineKeyboardMarkup:
    """Keywords submenu: list with delete + Add + Add bulk + Back."""
    rows = []
    for kw in keywords:
        kid = kw.get("id")
        word = kw.get("word", "")
        group_name = kw.get("group_name") or ""
        if kid is not None:
            label = (word[:22] + "…") if len(word) > 22 else word
            if group_name:
                label = f"{label} ({group_name[:12]}…)" if len(group_name) > 12 else f"{label} ({group_name})"
            label = (label[:35] + "…") if len(label) > 35 else label
            rows.append([
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"{ADMIN_KW_DEL}_{kid}",
                ),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить маркер", callback_data=ADMIN_KW_ADD)])
    rows.append([InlineKeyboardButton(text="📋 Добавить списком", callback_data=ADMIN_KW_BULK)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keyword_groups_keyboard(
    groups: list[dict],
    back: bool = True,
) -> InlineKeyboardMarkup:
    """Keyword groups submenu: list with open + Delete + Add + Back."""
    rows = []
    for g in groups:
        gid = g.get("id")
        name = g.get("name") or ""
        ch_display = g.get("channel_display_name") or g.get("channel_identifier") or ""
        if gid is not None:
            label = (name[:20] + "…") if len(name) > 20 else name
            if ch_display:
                label = f"{label} → {ch_display[:15]}…" if len(ch_display) > 15 else f"{label} → {ch_display}"
            label = (label[:35] + "…") if len(label) > 35 else label
            rows.append([
                InlineKeyboardButton(text=label, callback_data=f"{ADMIN_KG_OPEN}_{gid}"),
                InlineKeyboardButton(text="❌", callback_data=f"{ADMIN_KG_DEL}_{gid}"),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить группу", callback_data=ADMIN_KG_ADD)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keyword_group_detail_keyboard(
    group_id: int,
    keywords_in_group: list[dict],
    back: bool = True,
) -> InlineKeyboardMarkup:
    """Inside one group: list markers (delete), Add marker, Back."""
    rows = []
    for kw in keywords_in_group[:15]:
        kid = kw.get("id")
        word = kw.get("word", "")
        if kid is not None:
            label = (word[:28] + "…") if len(word) > 28 else word
            rows.append([
                InlineKeyboardButton(text=f"❌ {label}", callback_data=f"{ADMIN_KW_DEL}_{kid}"),
            ])
    if len(keywords_in_group) > 15:
        rows.append([InlineKeyboardButton(text="…", callback_data="admin_noop")])
    rows.append([InlineKeyboardButton(text="➕ Добавить маркер в группу", callback_data=f"{ADMIN_KG_ADD_KW}_{group_id}")])
    rows.append([InlineKeyboardButton(text="📋 Добавить списком", callback_data=f"{ADMIN_KG_BULK}_{group_id}")])
    rows.append([
        InlineKeyboardButton(text="📄 Вывести списком", callback_data=f"{ADMIN_KG_SHOW_ALL}_{group_id}"),
        InlineKeyboardButton(text="🗑 Очистить группу", callback_data=f"{ADMIN_KG_CLEAR}_{group_id}")
    ])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_KG)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_scheduled_list_keyboard(
    posts: list | None = None,
    back: bool = True,
    max_edit_buttons: int = 20,
) -> InlineKeyboardMarkup:
    """Under scheduled list: per post [Изменить] [Отменить], then Refresh, Back."""
    rows = []
    if posts:
        for p in posts[:max_edit_buttons]:
            pid = getattr(p, "id", None) or (p.get("id") if isinstance(p, dict) else None)
            if pid is None:
                continue
            rows.append([
                InlineKeyboardButton(text="Изменить", callback_data=f"{ADMIN_SCHED_EDIT}_{pid}"),
                InlineKeyboardButton(text="Отменить", callback_data=f"{ADMIN_SCHED_CANCEL}_{pid}"),
            ])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=ADMIN_SCHED_REFRESH)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_choose_group_keyboard(
    groups: list[dict],
    with_none: bool = True,
    back_data: str = ADMIN_KW,
) -> InlineKeyboardMarkup:
    """Choose keyword group (for adding keyword or bulk). with_none = add 'Без группы'."""
    rows = []
    for g in groups:
        gid = g.get("id")
        name = g.get("name") or ""
        if gid is not None:
            label = (name[:35] + "…") if len(name) > 35 else name
            rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_gr_{gid}")])
    if with_none:
        rows.append([InlineKeyboardButton(text="Без группы", callback_data="admin_gr_0")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_choose_target_channel_keyboard(
    channels: list[dict],
    back_data: str = ADMIN_KG,
) -> InlineKeyboardMarkup:
    """Choose target channel for new keyword group."""
    rows = []
    for ch in channels:
        cid = ch.get("id")
        display = ch.get("display_name") or ch.get("channel_identifier") or ""
        if cid is not None:
            label = (display[:35] + "…") if len(display) > 35 else display
            rows.append([InlineKeyboardButton(text=label, callback_data=f"admin_tc_{cid}")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=back_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_editors_keyboard(
    editors: list[dict],
    back: bool = True,
    super_admin_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Editors submenu: list with delete + Add + Back. super_admin_id cannot be removed."""
    rows = []
    for ed in editors:
        uid = ed.get("user_id")
        username = ed.get("username") or ""
        label = f"@{username}" if username else str(uid)
        if uid is None:
            continue
        if uid == super_admin_id:
            rows.append([
                InlineKeyboardButton(
                    text=f"🔒 {label} (главный)",
                    callback_data="admin_ed_noop",
                ),
            ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"{ADMIN_ED_DEL}_{uid}",
                ),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить редактора", callback_data=ADMIN_ED_ADD)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_admins_keyboard(
    admins_list: list[dict],
    back: bool = True,
    super_admin_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Admins submenu: list with delete + Add + Back. super_admin_id cannot be removed."""
    rows = []
    for ad in admins_list:
        uid = ad.get("user_id")
        username = ad.get("username") or ""
        label = f"@{username}" if username else str(uid)
        if uid is None:
            continue
        if uid == super_admin_id:
            rows.append([
                InlineKeyboardButton(
                    text=f"🔒 {label} (главный)",
                    callback_data="admin_adm_noop",
                ),
            ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text=f"❌ {label}",
                    callback_data=f"{ADMIN_ADM_DEL}_{uid}",
                ),
            ])
    rows.append([InlineKeyboardButton(text="➕ Добавить админа", callback_data=ADMIN_ADM_ADD)])
    if back:
        rows.append([InlineKeyboardButton(text="Назад", callback_data=ADMIN_MAIN)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

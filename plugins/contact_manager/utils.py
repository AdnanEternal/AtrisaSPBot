from splusthon import functions, types


async def get_contacts(client):
    """دریافت فهرست فعلی مخاطبین حساب."""
    result = await client(
        functions.contacts.GetContactsRequest(hash=0)
    )

    return list(getattr(result, "users", None) or [])


async def get_contact_count(client):
    """دریافت تعداد فعلی مخاطبین حساب."""
    contacts = await get_contacts(client)
    return len(contacts)





async def resolve_group_entity(client, chat_ref):
    """Resolve a group or channel by ID, username, or supported link."""

    raw = str(chat_ref).strip()

    if not raw:
        raise ValueError("شناسه یا آدرس گروه/کانال خالی است.")

    # شناسه عددی: از گفتگوهای شناخته‌شده حساب پیدا کن.
    if raw.lstrip("-").isdigit():
        wanted_id = int(raw)

        async for dialog in client.iter_dialogs():
            entity = getattr(dialog, "entity", None)

            if not isinstance(entity, (types.Chat, types.Channel)):
                continue

            entity_id = getattr(entity, "id", None)
            dialog_id = getattr(dialog, "id", None)

            if wanted_id == entity_id or wanted_id == dialog_id:
                return entity

        raise ValueError(
            "گروه یا کانال با این شناسه در گفتگوهای حساب پیدا نشد. "
            "عضویت حساب و شناسه را بررسی کن."
        )

    # نام کاربری یا لینک قابل شناسایی توسط SPlusthon
    entity = await client.get_entity(raw)

    if isinstance(entity, (types.Chat, types.Channel)):
        return entity

    raise ValueError("این شناسه به گروه یا کانال اشاره نمی‌کند.")


async def get_group_member_stats(client, chat_ref):
    """دریافت آمار کل اعضا بدون ذخیره فهرست کاربران."""

    entity = await resolve_group_entity(client, chat_ref)

    total = None

    if isinstance(entity, types.Channel):
        # شامل کانال عادی و سوپرگروه مبتنی بر Channel
        result = await client(
            functions.channels.GetFullChannelRequest(entity)
        )

        full_chat = getattr(result, "full_chat", None)
        total = getattr(full_chat, "participants_count", None)

    elif isinstance(entity, types.Chat):
        # برای گروه معمولی از شمارنده موجود در Entity استفاده کن.
        total = getattr(entity, "participants_count", None)

    if total is None:
        raise ValueError(
            "API تعداد کل اعضای این گروه/کانال را ارائه نکرد."
        )

    return {
        "title": getattr(entity, "title", None),
        "total": int(total),
    }
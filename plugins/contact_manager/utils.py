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





async def resolve_group_entity(client, group_ref):
    """پیدا کردن Entity گروه با شناسه یا نام کاربری."""

    raw = str(group_ref).strip()

    if not raw:
        raise ValueError("شناسه یا آدرس گروه خالی است.")

    # شناسه عددی: ابتدا گروه را در گفتگوهای حساب پیدا کن.
    if raw.lstrip("-").isdigit():
        wanted_id = int(raw)

        async for dialog in client.iter_dialogs():
            if not getattr(dialog, "is_group", False):
                continue

            entity = getattr(dialog, "entity", None)
            if entity is None:
                continue

            entity_id = getattr(entity, "id", None)
            dialog_id = getattr(dialog, "id", None)

            if wanted_id == entity_id or wanted_id == dialog_id:
                return entity

        raise ValueError(
            "این شناسه در گفتگوهای حساب پیدا نشد. "
            "عضویت یا دسترسی حساب به گروه و شناسه را بررسی کن؛ "
            "برای گروه عمومی می‌توانی نام کاربری یا لینک معتبرش را بدهی."
        )

    # نام کاربری یا لینک گروه
    entity = await client.get_entity(raw)

    if isinstance(entity, types.Chat):
        return entity

    if (
        isinstance(entity, types.Channel)
        and getattr(entity, "megagroup", False)
    ):
        return entity

    raise ValueError("موجودیت پیدا شده یک گروه قابل پشتیبانی نیست.")


async def get_group_member_stats(client, group_ref):
    """دریافت آمار کل اعضا بدون خروجی گرفتن از فهرست هویتی."""

    entity = await resolve_group_entity(client, group_ref)

    total = None

    if isinstance(entity, types.Channel):
        # برای گروه‌های مبتنی بر Channel، تعداد را از اطلاعات کامل گروه بگیر.
        result = await client(
            functions.channels.GetFullChannelRequest(entity)
        )

        full_chat = getattr(result, "full_chat", None)
        total = getattr(full_chat, "participants_count", None)

    elif isinstance(entity, types.Chat):
        # ابتدا از شمارنده موجود در Entity استفاده کن.
        total = getattr(entity, "participants_count", None)

        # در گروه‌های قدیمی‌تر، اگر شمارنده موجود نبود، از پاسخ
        # GetFullChat فقط تعداد رکوردهای اعضا را محاسبه کن.
        if total is None:
            result = await client(
                functions.messages.GetFullChatRequest(entity.id)
            )

            full_chat = getattr(result, "full_chat", None)
            participants = getattr(full_chat, "participants", None)
            rows = getattr(participants, "participants", None)

            if rows is not None:
                total = len(rows)

    if total is None:
        raise ValueError(
            "API تعداد اعضای این گروه را برنگرداند."
        )

    return {
        "title": getattr(entity, "title", None),
        "total": int(total),
    }
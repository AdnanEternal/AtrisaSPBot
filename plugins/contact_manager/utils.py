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





async def resolve_chat_entity(client, chat_ref):
    """حل شناسه، نام کاربری یا لینک گروه و کانال."""

    chat_ref = str(chat_ref).strip()

    if not chat_ref:
        raise ValueError("شناسه یا آدرس گروه/کانال خالی است.")

    if chat_ref.lstrip("-").isdigit():
        wanted_id = int(chat_ref)

        async for dialog in client.iter_dialogs():
            entity = getattr(dialog, "entity", None)

            if not isinstance(entity, (types.Chat, types.Channel)):
                continue

            if (
                getattr(entity, "id", None) == wanted_id
                or getattr(dialog, "id", None) == wanted_id
            ):
                return entity

        raise ValueError(
            "گروه یا کانال در گفتگوهای حساب پیدا نشد."
        )

    entity = await client.get_entity(chat_ref)

    if isinstance(entity, (types.Chat, types.Channel)):
        return entity

    raise ValueError("موجودیت پیدا شده گروه یا کانال نیست.")


async def get_official_member_count(client, entity):
    """دریافت تعداد رسمی اعضا از API."""

    if isinstance(entity, types.Channel):
        result = await client(
            functions.channels.GetFullChannelRequest(entity)
        )
        full_chat = getattr(result, "full_chat", None)
        count = getattr(full_chat, "participants_count", None)

    elif isinstance(entity, types.Chat):
        count = getattr(entity, "participants_count", None)

    else:
        raise TypeError("نوع موجودیت پشتیبانی نمی‌شود.")

    if count is None:
        raise ValueError(
            "API تعداد رسمی اعضا را ارائه نکرد."
        )

    return int(count)


async def get_chat_member_stats(client, chat_ref):
    """جمع‌آوری آمار رسمی گروه یا کانال."""

    entity = await resolve_chat_entity(client, chat_ref)
    total = await get_official_member_count(client, entity)

    return {
        "title": getattr(entity, "title", None),
        "total_members": total,
    }
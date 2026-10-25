from splusthon import functions


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

async def get_group_member_stats(client, group_id: int):
    """محاسبه آمار اعضای گروه بدون ذخیره فهرست کاربران."""

    group = await client.get_entity(int(group_id))
    members = await client.get_participants(group, limit=None)

    total = getattr(members, "total", None)
    if not isinstance(total, int):
        total = getattr(group, "participants_count", None)

    if not isinstance(total, int):
        total = len(members)

    extractable = sum(
        getattr(member, "access_hash", None) is not None
        for member in members
    )

    return {
        "total": total,
        "received": len(members),
        "extractable": extractable,
    }

from splusthon import functions
from splusthon import types
from splusthon.tl.functions.channels import GetParticipantsRequest
from splusthon.tl.types import ChannelParticipantsSearch


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


async def get_group_members(client, group_id, limit=25):
    """دریافت تعداد مشخصی از کاربران قابل‌مشاهدهٔ گروه."""

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer")

    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")

    members = await client.get_participants(
        int(group_id),
        limit=limit,
    )

    return list(members or [])[:limit]


async def add_user_to_contacts(client, user):
    """افزودن یک کاربر مشخص به مخاطبین."""
    access_hash = getattr(user, "access_hash", None)

    if access_hash is None:
        raise ValueError("کاربر access_hash ندارد")

    return await client(
        functions.contacts.AddContactRequest(
            id=types.InputUser(
                user_id=user.id,
                access_hash=access_hash,
            ),
            first_name=getattr(user, "first_name", "") or "",
            last_name=getattr(user, "last_name", "") or "",
            phone="",
        )
    )

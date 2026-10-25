
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


async def get_group_members(client, group_id, limit=2):
    """دریافت حداکثر تعداد مشخصی از اعضای گروه یا کانال."""
    if not 1 <= limit <= 2:
        raise ValueError("limit must be between 1 and 2")

    group = await client.get_entity(int(group_id))

    result = await client(
        GetParticipantsRequest(
            channel=group,
            filter=ChannelParticipantsSearch(""),
            limit=limit,
            offset=0,
        )
    )

    return list(getattr(result, "users", None) or [])[:limit]


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

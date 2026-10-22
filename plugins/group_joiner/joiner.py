from splusthon import utils
from splusthon.tl import types

from splusthon.tl.functions.channels import (
    JoinChannelRequest,
)
from splusthon.tl.functions.messages import (
    ImportChatInviteRequest,
)


async def join_by_chat_id(
    client,
    chat_id: int,
):
    """
    عضویت در یک کانال یا گروه کانال‌محور،
    فقط با استفاده از شناسهٔ عددی.

    chat_id می‌تواند شناسهٔ خام کانال یا شناسهٔ
    علامت‌گذاری‌شدهٔ SPlusthon باشد.
    """

    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "chat_id باید یک عدد صحیح باشد."
        ) from exc

    if chat_id == 0:
        raise ValueError(
            "chat_id نمی‌تواند صفر باشد."
        )

    # اگر شناسه مثبت باشد، آن را شناسهٔ خام کانال
    # در نظر می‌گیریم.
    if chat_id > 0:
        channel_id = chat_id

    else:
        # شناسه‌های علامت‌گذاری‌شدهٔ SPlusthon
        # نوع چت را مشخص می‌کنند.
        entity_id, peer_type = utils.resolve_id(
            chat_id
        )

        if peer_type is not types.PeerChannel:
            raise ValueError(
                "این شناسه متعلق به یک کانال نیست. "
                "عضویت در گروه‌های معمولی فقط با chat_id "
                "از این طریق پشتیبانی نمی‌شود."
            )

        channel_id = entity_id

    if channel_id <= 0:
        raise ValueError(
            "شناسهٔ کانال نامعتبر است."
        )

    # دریافت موجودیت بر اساس شناسه؛
    # هیچ username یا لینکی استفاده نمی‌شود.
    channel = await client.get_entity(
        types.PeerChannel(channel_id)
    )

    if not isinstance(
        channel,
        (
            types.Channel,
            types.ChannelForbidden,
        ),
    ):
        raise ValueError(
            "شناسه به یک کانال معتبر اشاره نمی‌کند."
        )

    return await client(
        JoinChannelRequest(channel)
    )


async def join_by_username(
    client,
    username: str,
):
    """عضویت در کانال عمومی از طریق نام کاربری."""

    channel = await client.get_entity(username)

    if not isinstance(
        channel,
        (
            types.Channel,
            types.ChannelForbidden,
        ),
    ):
        raise ValueError(
            "نام کاربری به یک کانال معتبر اشاره نمی‌کند."
        )

    return await client(
        JoinChannelRequest(channel)
    )


async def join_by_invite_hash(
    client,
    invite_hash: str,
):
    """عضویت از طریق هش لینک دعوت خصوصی."""

    return await client(
        ImportChatInviteRequest(invite_hash)
    )
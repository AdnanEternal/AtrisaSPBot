
from splusthon import utils
from splusthon.tl import types

from splusthon.tl.functions.channels import (
    JoinChannelRequest,
)

from splusthon.tl.functions.messages import (
    ImportChatInviteRequest,
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

    print(
        "🔎 Group Joiner - Public link resolved: "
        f"entity_type={type(channel).__name__}, "
        f"channel_id={channel.id}, "
        f"splus_peer_id={utils.get_peer_id(channel)}, "
        f"username={getattr(channel, 'username', None)!r}, "
        f"has_access_hash="
        f"{getattr(channel, 'access_hash', None) is not None}"
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

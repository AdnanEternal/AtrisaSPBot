from splusthon import utils
from splusthon.tl import types

from splusthon.tl.functions.channels import (
    GetChannelsRequest,
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
    دریافت موجودیت کانال از API با شناسهٔ عددی،
    سپس تلاش برای عضویت با موجودیت واقعی.
    """

    raw_id = str(chat_id).strip()

    try:
        chat_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "chat_id باید یک عدد صحیح باشد."
        ) from exc

    if chat_id == 0:
        raise ValueError("chat_id نمی‌تواند صفر باشد.")

    # شناسهٔ استاندارد SPlusthon
    if chat_id < -1_000_000_000_000:
        channel_id, peer_type = utils.resolve_id(chat_id)

        if peer_type is not types.PeerChannel:
            raise ValueError(
                "شناسهٔ استاندارد واردشده متعلق به کانال نیست."
            )

    # قالب رایج -100<ID>
    elif raw_id.startswith("-100") and raw_id[4:].isdigit():
        channel_id = int(raw_id[4:])

    # شناسهٔ خام مثبت
    elif chat_id > 0:
        channel_id = chat_id

    else:
        raise ValueError(
            "قالب شناسه شناخته‌شده نیست."
        )

    if channel_id <= 0:
        raise ValueError("شناسهٔ کانال نامعتبر است.")

    # مرحلهٔ اول: درخواست مستقیم به API برای دریافت موجودیت.
    # عمداً به get_entity و کش قبلی وابسته نیستیم.
    response = await client(
        GetChannelsRequest(
            id=[
                types.InputChannel(
                    channel_id=channel_id,
                    access_hash=0,
                )
            ]
        )
    )

    chats = getattr(response, "chats", None) or []

    channel = next(
        (
            item
            for item in chats
            if getattr(item, "id", None) == channel_id
        ),
        None,
    )

    if channel is None:
        raise ValueError(
            f"API هیچ موجودیتی برای کانال {channel_id} برنگرداند."
        )

    if not isinstance(
        channel,
        (types.Channel, types.ChannelForbidden),
    ):
        raise ValueError(
            f"موجودیت دریافت‌شده کانال قابل عضویت نیست: "
            f"{type(channel).__name__}"
        )

    # موجودیت برگشتی API را مستقیم استفاده می‌کنیم؛
    # این موجودیت به جای access_hash=0، اطلاعات واقعی پاسخ را دارد.
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
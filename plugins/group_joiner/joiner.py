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
    ابتدا تلاش می‌کند موجودیت کانال را از کش نشست دریافت کند.
    اگر در کش نباشد، SPlusthon خودش از API برای resolve کردن
    شناسه استفاده می‌کند.
    """

    raw_id = str(chat_id).strip()

    try:
        chat_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "chat_id باید یک عدد صحیح باشد."
        ) from exc

    if chat_id == 0:
        raise ValueError(
            "chat_id نمی‌تواند صفر باشد."
        )

    # شناسهٔ علامت‌گذاری‌شدهٔ استاندارد SPlusthon
    if chat_id < -1_000_000_000_000:
        channel_id, peer_type = utils.resolve_id(chat_id)

        if peer_type is not types.PeerChannel:
            raise ValueError(
                "شناسهٔ استاندارد واردشده متعلق به کانال نیست."
            )

    # قالب رایج -100<ID> که در ورودی پروژه پشتیبانی می‌کنیم
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
        raise ValueError(
            "شناسهٔ کانال نامعتبر است."
        )

    # مهم: به‌جای GetChannelsRequest با access_hash=0،
    # از API عمومی کتابخانه استفاده می‌کنیم.
    # SPlusthon ابتدا کش حافظه و کش نشست را بررسی می‌کند
    # و در صورت نیاز تلاش می‌کند موجودیت را از API بگیرد.
    try:
        channel = await client.get_entity(
            types.PeerChannel(channel_id)
        )

    except (ValueError, IndexError, KeyError) as exc:
        raise ValueError(
            f"کانال با شناسهٔ داخلی {channel_id} resolve نشد. "
            "ممکن است موجودیت در کش نشست نباشد و API هم "
            "نتواند آن را فقط با شناسه پیدا کند. "
            "اگر کانال عمومی است، ابتدا لینک یا نام کاربری آن "
            "را در همین نشست resolve کن و سپس شناسه را امتحان کن."
        ) from exc

    if not isinstance(
        channel,
        (
            types.Channel,
            types.ChannelForbidden,
        ),
    ):
        raise ValueError(
            "موجودیت دریافت‌شده از نوع قابل‌قبول برای "
            f"عضویت در کانال نیست: {type(channel).__name__}"
        )

    print(
        "✅ Group Joiner - Channel resolved by ID: "
        f"input_id={raw_id}, "
        f"channel_id={channel.id}, "
        f"splus_peer_id={utils.get_peer_id(channel)}, "
        f"username={getattr(channel, 'username', None)!r}"
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
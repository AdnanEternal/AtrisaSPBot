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
    تلاش برای عضویت در کانال با شناسهٔ عددی.

    قالب‌های پشتیبانی‌شده:
    - شناسهٔ استاندارد SPlusthon
    - قالب قدیمی -100<ID>
    - شناسهٔ خام مثبت کانال

    اگر شناسه به‌تنهایی برای resolve کردن کانال کافی نباشد،
    تلاش مستقیم با InputChannel نیز انجام می‌شود.
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

    # قالب استاندارد شناسه‌های علامت‌گذاری‌شدهٔ SPlusthon:
    # -(1_000_000_000_000 + channel_id)
    if chat_id < -1_000_000_000_000:
        channel_id, peer_type = utils.resolve_id(chat_id)

        if peer_type is not types.PeerChannel:
            raise ValueError(
                "شناسهٔ واردشده متعلق به کانال نیست."
            )

    # پشتیبانی از قالب -100<ID>، مانند -10018050783
    elif raw_id.startswith("-100") and raw_id[4:].isdigit():
        channel_id = int(raw_id[4:])

    # شناسهٔ خام مثبت کانال
    elif chat_id > 0:
        channel_id = chat_id

    else:
        raise ValueError(
            "این شناسه با قالب شناخته‌شدهٔ کانال سازگار نیست. "
            "شناسهٔ گروه معمولی نیز لزوماً برای عضویت کافی نیست."
        )

    if channel_id <= 0:
        raise ValueError(
            "شناسهٔ کانال نامعتبر است."
        )

    # ابتدا از روش معمول استفاده می‌کنیم تا اگر کانال
    # در کش یا نشست شناخته شده است، access_hash واقعی را بگیریم.
    try:
        channel = await client.get_entity(
            types.PeerChannel(channel_id)
        )

    except (ValueError, IndexError):
        channel = None

    if channel is not None:
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

    # اگر resolve معمولی شکست خورد، تلاش مستقیم با شناسه.
    # در این مسیر access_hash واقعی در دسترس نیست؛
    # بنابراین موفقیت به پشتیبانی سرور از این درخواست بستگی دارد.
    try:
        input_channel = types.InputChannel(
            channel_id=channel_id,
            access_hash=0,
        )

        return await client(
            JoinChannelRequest(input_channel)
        )

    except IndexError as exc:
        raise ValueError(
            "SPlusthon نتوانست کانال را با این شناسه پیدا کند. "
            "ممکن است شناسه اشتباه باشد یا access_hash واقعی "
            "برای این نشست در دسترس نباشد."
        ) from exc


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
import re
from typing import TYPE_CHECKING

from splusthon import events
from splusthon.errors import (
    FloodWaitError,
    RPCError,
)

from splusthon.tl.functions.messages import (
    ImportChatInviteRequest,
)

from core.decorators import on_event
from core.permissions import is_owner


if TYPE_CHECKING:
    from .plugin import GroupJoinerPlugin


# فعلاً فقط لینک دعوت خصوصی گروه‌های سروش‌پلاس.
_INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/joingroup/"
    r"([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def _extract_invite_hash(
    text: str,
) -> str | None:
    match = _INVITE_LINK_RE.search(
        text or ""
    )

    if match is None:
        return None

    return match.group(1)


@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GroupJoinerPlugin",
    event: events.NewMessage.Event,
) -> None:
    # فقط PV
    if not event.is_private:
        return

    # فقط Owner
    if not is_owner(event.sender_id):
        return

    text = (
        event.raw_text or ""
    ).strip()

    invite_hash = _extract_invite_hash(
        text
    )

    if invite_hash is None:
        return

    try:
        await self.client(
            ImportChatInviteRequest(
                invite_hash
            )
        )

    except FloodWaitError as exc:
        seconds = getattr(
            exc,
            "seconds",
            None,
        )

        if seconds is not None:
            await event.reply(
                "⏳ سروش‌پلاس موقتاً درخواست‌های "
                f"ورود را محدود کرده است.\n"
                f"زمان انتظار: {seconds} ثانیه"
            )
        else:
            await event.reply(
                "⏳ سروش‌پلاس موقتاً درخواست‌های "
                "ورود را محدود کرده است."
            )

        return

    except RPCError as exc:
        error_text = str(exc).upper()

        if "USER_ALREADY_JOINED" in error_text:
            await event.reply(
                "ℹ️ آتریسا از قبل عضو این گروه است."
            )
            return

        print(
            "❌ Group Joiner RPC error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ ورود به گروه ناموفق بود.\n"
            f"خطا: `{type(exc).__name__}`"
        )
        return

    except Exception as exc:
        print(
            "❌ Group Joiner unexpected error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ هنگام ورود به گروه خطای "
            "غیرمنتظره‌ای رخ داد."
        )
        return

    await event.reply(
        "✅ آتریسا با موفقیت وارد گروه شد."
    )
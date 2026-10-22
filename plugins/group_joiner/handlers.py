
import re
from typing import TYPE_CHECKING

from splusthon import events
from splusthon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    RPCError,
)
from splusthon.tl.functions.messages import (
    ImportChatInviteRequest,
)
from splusthon.tl.functions.channels import (
    JoinChannelRequest,
)

from core.decorators import on_event
from core.permissions import is_owner


if TYPE_CHECKING:
    from .plugin import GroupJoinerPlugin


# لینک دعوت خصوصی:
# https://splus.ir/joingroup/INVITE_HASH
_INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/joingroup/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# لینک عمومی گروه یا کانال:
# https://splus.ir/USERNAME
# مسیر joingroup عمداً از این الگو مستثنا شده است.
_PUBLIC_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/"
    r"(?!joingroup(?:/|[?#\s]|$))"
    r"([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


def _extract_join_target(
    text: str,
) -> tuple[str, str] | None:
    text = text or ""

    invite_match = _INVITE_LINK_RE.search(text)

    if invite_match is not None:
        return "invite", invite_match.group(1)

    public_match = _PUBLIC_LINK_RE.search(text)

    if public_match is not None:
        return "public", public_match.group(1)

    return None


@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GroupJoinerPlugin",
    event: events.NewMessage.Event,
) -> None:
    # فقط دایرکت
    if not event.is_private:
        return

    # فقط مالک ربات
    if not is_owner(event.sender_id):
        return

    text = (event.raw_text or "").strip()

    target = _extract_join_target(text)

    if target is None:
        return

    target_type, target_value = target

    # لینک دعوت خصوصی و لینک عمومی دو API متفاوت دارند.
    link_description = (
        "لینک دعوت"
        if target_type == "invite"
        else "لینک عمومی"
    )

    try:
        if target_type == "invite":
            request = ImportChatInviteRequest(target_value)

        else:
            # ابتدا نام کاربری را به موجودیت واقعی کانال تبدیل کن.
            channel = await self.client.get_entity(target_value)

            # سپس درخواست عضویت را با موجودیت کانال بفرست.
            request = JoinChannelRequest(channel)

        await self.client(request)

    except ValueError as exc:
        print(
            "❌ Group Joiner - "
            f"Resolve کردن مقصد ناموفق بود: {exc}"
        )

        await event.reply(
            "❌ آتریسا نتوانست مقصد لینک عمومی را پیدا کند.\n"
            f"نام کاربری: `{target_value}`\n"
            "بررسی کن لینک درست باشد و مقصد یک کانال یا گروه عمومی باشد."
        )
        return

    except FloodWaitError as exc:
        seconds = getattr(exc, "seconds", None)

        message = (
            "⏳ سروش‌پلاس موقتاً درخواست‌های عضویت "
            "را محدود کرده است."
        )

        if seconds is not None:
            message += f"\nزمان انتظار: {seconds} ثانیه"

        await event.reply(message)
        return

    except ChannelPrivateError:
        await event.reply(
            "❌ آتریسا نتوانست وارد این گروه یا کانال شود.\n"
            "🔒 ممکن است مقصد خصوصی باشد، لینک معتبر نباشد "
            "یا دسترسی آتریسا محدود شده باشد."
        )
        return

    except RPCError as exc:
        error_details = (
            f"{type(exc).__name__} {exc}"
        ).upper()

        if (
            "USER_ALREADY_JOINED" in error_details
            or "USER_ALREADY_PARTICIPANT" in error_details
        ):
            await event.reply(
                "ℹ️ آتریسا از قبل عضو این گروه یا کانال است."
            )
            return

        if "INVITE_REQUEST_SENT" in error_details:
            await event.reply(
                "⏳ درخواست عضویت ارسال شد و در انتظار "
                "تأیید مدیر گروه یا کانال است."
            )
            return

        print(
            "❌ Group Joiner RPC error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ ورود به گروه یا کانال ناموفق بود.\n"
            f"نوع لینک: {link_description}\n"
            f"خطا: `{type(exc).__name__}`"
        )
        return

    except Exception as exc:
        print(
            "❌ Group Joiner unexpected error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ هنگام ورود به گروه یا کانال، "
            "خطای غیرمنتظره‌ای رخ داد."
        )
        return

    await event.reply(
        "✅ آتریسا با موفقیت وارد گروه یا کانال شد."
    )

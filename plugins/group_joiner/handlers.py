from typing import TYPE_CHECKING

from splusthon import events
from splusthon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    RPCError,
)

from core.decorators import on_event
from core.permissions import is_owner

from . import joiner
from .parser import extract_join_target


if TYPE_CHECKING:
    from .plugin import GroupJoinerPlugin


@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GroupJoinerPlugin",
    event: events.NewMessage.Event,
) -> None:
    # فقط دایرکت
    if not event.is_private:
        return

    # فقط مالک پلاگین
    if not is_owner(event.sender_id):
        return

    text = (event.raw_text or "").strip()

    target = extract_join_target(text)

    if target is None:
        return

    target_type, target_value = target

    link_description = (
        "لینک دعوت"
        if target_type == "invite"
        else "لینک عمومی"
    )

    try:
        if target_type == "invite":
            await joiner.join_by_invite_hash(
                self.client,
                target_value,
            )

        else:
            await joiner.join_by_username(
                self.client,
                target_value,
            )

    except ValueError as exc:
        print(
            "❌ Group Joiner - "
            f"Resolve error: {exc}"
        )

        await event.reply(
            "❌ آتریسا نتوانست مقصد لینک عمومی را پیدا کند.\n"
            f"نام کاربری: `{target_value}`\n"
            "بررسی کن لینک درست باشد و مقصد قابل دسترسی باشد."
        )
        return

    except FloodWaitError as exc:
        seconds = getattr(
            exc,
            "seconds",
            None,
        )

        message = (
            "⏳ سروش‌پلاس موقتاً درخواست‌های عضویت "
            "را محدود کرده است."
        )

        if seconds is not None:
            message += (
                f"\nزمان انتظار: {seconds} ثانیه"
            )

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
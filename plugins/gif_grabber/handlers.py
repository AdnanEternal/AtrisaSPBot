from typing import TYPE_CHECKING

from splusthon import events
from splusthon.tl.functions.messages import (
    SaveGifRequest,
    GetSavedGifsRequest
)
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from core.decorators import command, on_event


if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin



MAX_GIFS_PER_COMMAND = 100


@command(
    name="دریافت",
    permission="owner",
    chat_type="all",
    description="گیف‌های یک کانال را به Saved GIFs اضافه می‌کند.",
    native_name="fetch_gifs",
)
async def fetch_gifs(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    args = getattr(event, "args", [])

    if len(args) != 2:
        await event.reply(
            "❌ تعداد و شناسهٔ کانال را وارد کن.\n"
            "مثال:\n"
            + self.command_usage(
                event.command,
                "100 <channel_id>",
                event=event,
            )
        )
        return

    try:
        requested_count = int(args[0])
        channel_id = int(args[1])
    except (TypeError, ValueError):
        await event.reply(
            "❌ تعداد گیف‌ها و شناسهٔ کانال باید عدد باشند."
        )
        return

    if requested_count <= 0:
        await event.reply(
            "❌ تعداد گیف‌ها باید بیشتر از صفر باشد."
        )
        return

    target_count = min(
        requested_count,
        MAX_GIFS_PER_COMMAND,
    )

    # --------------------------------------------------
    # Resolve channel
    # --------------------------------------------------

    try:
        channel = await self.client.get_entity(
            channel_id
        )
    except Exception as exc:
        await event.reply(
            "❌ نتوانستم کانال را با این شناسه پیدا کنم.\n"
            f"جزئیات: {exc}"
        )
        return

    if not isinstance(channel, types.Channel):
        await event.reply(
            "❌ شناسهٔ واردشده به یک کانال معتبر اشاره نمی‌کند."
        )
        return

    await event.reply(
        f"⏳ شروع بررسی کانال...\n"
        f"🎯 هدف: ذخیرهٔ حداکثر {target_count} گیف یکتا"
    )

    saved_count = 0
    failed_count = 0
    scanned_count = 0

    seen_document_ids = set()
    stopped_reason = None

    # --------------------------------------------------
    # Scan channel history, newest to oldest
    # --------------------------------------------------

    try:
        async for message in self.client.iter_messages(
            channel,
            limit=None,
        ):
            scanned_count += 1

            gif = message.gif

            if gif is None:
                continue

            document_id = getattr(
                gif,
                "id",
                None,
            )

            if document_id is None:
                continue

            # یک سند ممکن است در چند پیام تکرار شده باشد.
            if document_id in seen_document_ids:
                continue

            seen_document_ids.add(document_id)

            # ذخیره در Saved GIFs واقعی حساب
            try:
                await self.client(
                    SaveGifRequest(
                        id=gif,
                        unsave=False,
                    )
                )

            except FloodWaitError as exc:
                failed_count += 1

                wait_seconds = getattr(
                    exc,
                    "seconds",
                    None,
                )

                stopped_reason = (
                    "محدودیت تعداد درخواست‌های سرور"
                    + (
                        f"؛ زمان انتظار اعلام‌شده: "
                        f"{wait_seconds} ثانیه"
                        if wait_seconds is not None
                        else ""
                    )
                )

                print(
                    "⚠️ GIF Grabber - "
                    f"FloodWait هنگام ذخیرهٔ گیف: {exc}"
                )
                break

            except Exception as exc:
                failed_count += 1

                print(
                    "❌ GIF Grabber - "
                    f"ذخیرهٔ گیف {document_id} ناموفق بود: "
                    f"{exc}"
                )
                continue

            saved_count += 1

            print(
                "✅ GIF Grabber - "
                f"ذخیره شد: {document_id} "
                f"({saved_count}/{target_count})"
            )

            if saved_count >= target_count:
                break

    except Exception as exc:
        stopped_reason = (
            f"خطا هنگام پیمایش تاریخچهٔ کانال: {exc}"
        )

        print(
            "❌ GIF Grabber - "
            f"پیمایش کانال ناموفق شد: {exc}"
        )

    # --------------------------------------------------
    # Final report
    # --------------------------------------------------

    result_lines = [
        "📥 عملیات دریافت گیف تمام شد.",
        f"✅ ذخیره‌های موفق: {saved_count}",
        f"❌ ذخیره‌های ناموفق: {failed_count}",
        f"🔎 پیام‌های بررسی‌شده: {scanned_count}",
    ]

    if requested_count > MAX_GIFS_PER_COMMAND:
        result_lines.append(
            f"ℹ️ سقف هر اجرا {MAX_GIFS_PER_COMMAND} گیف است."
        )

    if stopped_reason:
        result_lines.append(
            f"⚠️ علت توقف: {stopped_reason}"
        )
    elif saved_count < target_count:
        result_lines.append(
            "ℹ️ تاریخچه تمام شد یا گیف یکتای بیشتری پیدا نشد."
        )

    await event.reply(
        "\n".join(result_lines)
    )





async def get_saved_gifs(client) -> list:
    result = await client(
        GetSavedGifsRequest(hash=0)
    )

    return list(
        getattr(result, "gifs", None) or []
    )





@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    

    if (
        event.is_group is not True
        and event.is_channel is not True
    ):
        return

    gif = event.message.gif

    if gif is None:
        return

    try:
        await self.client(
            SaveGifRequest(
                id=gif,
                unsave=False,
            )
        )

    except Exception as exc:
        print(
            "❌ GIF Grabber - "
            f"ذخیره گیف ناموفق بود: {exc}"
        )
        return

    # print("✅ GIF Grabber - گیف به Saved GIFs اضافه شد.")
    print(event)
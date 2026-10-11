from typing import TYPE_CHECKING

from splusthon import events
from splusthon.tl.functions.messages import SaveGifRequest,GetSavedGifsRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from core.decorators import command, on_event


if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


MAX_GIFS_PER_COMMAND = 200
# حداکثر تعداد درخواست‌های حذف هم‌زمان
GIF_DELETE_CONCURRENCY = 5




@command(
    name="پاکسازی_گیف",
    permission="owner",
    chat_type="all",
    description="گیف‌های Saved GIFs را حذف می‌کند.",
    native_name="clear_saved_gifs",
)

async def clear_saved_gifs(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    import asyncio

    concurrency = max(1, int(GIF_DELETE_CONCURRENCY))

    # دریافت فهرست گیف‌های ذخیره‌شده
    try:
        response = await self.client(
            GetSavedGifsRequest(hash=0)
        )
    except Exception as exc:
        await event.reply(
            "❌ دریافت فهرست Saved GIFs ناموفق بود.\n"
            f"جزئیات: {exc}"
        )
        return

    gifs = getattr(response, "gifs", None)

    if gifs is None:
        await event.reply(
            "❌ پاسخ سرور شامل فهرست گیف‌ها نبود؛ "
            "هیچ گیفی حذف نشد."
        )
        return

    if not gifs:
        await event.reply(
            "ℹ️ فهرست Saved GIFs خالی است."
        )
        return

    total_count = len(gifs)
    removed_count = 0
    failed_count = 0
    attempted_count = 0
    stopped_reason = None

    await event.reply(
        "🧹 شروع پاکسازی Saved GIFs...\n"
        f"🎯 تعداد گیف‌ها: {total_count}\n"
        f"⚡ درخواست هم‌زمان: {concurrency}"
    )

    async def remove_gif(gif):
        document_id = getattr(gif, "id", None)

        if document_id is None:
            return "failed", "شناسهٔ گیف موجود نیست"

        try:
            await self.client(
                SaveGifRequest(
                    id=gif,
                    unsave=True,
                )
            )
            return "success", document_id

        except FloodWaitError as exc:
            return "flood", (
                document_id,
                getattr(exc, "seconds", None),
                str(exc),
            )

        except Exception as exc:
            return "failed", (
                document_id,
                str(exc),
            )

    # اجرای دسته‌های محدود؛ در هر دسته حداکثر
    # concurrency درخواست حذف اجرا می‌شود.
    for start in range(0, total_count, concurrency):
        batch = gifs[start:start + concurrency]

        results = await asyncio.gather(
            *(remove_gif(gif) for gif in batch)
        )

        attempted_count += len(batch)

        flood_detected = False

        for status, details in results:
            if status == "success":
                removed_count += 1
                continue

            failed_count += 1

            if status == "flood":
                flood_detected = True
                document_id, wait_seconds, error_text = details

                stopped_reason = (
                    "محدودیت درخواست‌های سرور"
                    + (
                        f"؛ زمان انتظار اعلام‌شده: "
                        f"{wait_seconds} ثانیه"
                        if wait_seconds is not None
                        else ""
                    )
                )

                print(
                    "⚠️ GIF Grabber - "
                    f"FloodWait هنگام حذف گیف "
                    f"{document_id}: {error_text}"
                )
            else:
                if isinstance(details, tuple):
                    document_id, error_text = details
                else:
                    document_id = "نامشخص"
                    error_text = details

                print(
                    "❌ GIF Grabber - "
                    f"حذف گیف {document_id} ناموفق بود: "
                    f"{error_text}"
                )

        # درخواست‌های دستهٔ جاری تمام شده‌اند؛
        # در صورت FloodWait دستهٔ بعدی را شروع نکن.
        if flood_detected:
            break

    skipped_count = total_count - attempted_count

    result_lines = [
        "🧹 گزارش پاکسازی Saved GIFs",
        f"📋 تعداد اولیه: {total_count}",
        f"⚡ سقف درخواست هم‌زمان: {concurrency}",
        f"📨 گیف‌های بررسی‌شده: {attempted_count}",
        f"✅ حذف موفق: {removed_count}",
        f"❌ حذف ناموفق: {failed_count}",
        f"⏭️ بررسی‌نشده: {skipped_count}",
    ]

    if stopped_reason:
        result_lines.append(
            f"⚠️ پاکسازی متوقف شد: {stopped_reason}"
        )

    await event.reply("\n".join(result_lines))






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
    # Resolve chat from dialogs
    # --------------------------------------------------

    try:
        dialogs = await self.client.get_dialogs()

        target_dialog = next(
            (
                dialog
                for dialog in dialogs
                if dialog.id == channel_id
            ),
            None,
        )

        # بعضی شناسه‌ها ممکن است با قالب متفاوت وارد شوند.
        # اگر تطبیق مستقیم انجام نشد، مقدار مثبت را هم بررسی می‌کنیم.
        if target_dialog is None and channel_id > 0:
            target_dialog = next(
                (
                    dialog
                    for dialog in dialogs
                    if abs(dialog.id) == channel_id
                ),
                None,
            )

        if target_dialog is None:
            await event.reply(
                "❌ این شناسه در گفت‌وگوهای قابل‌دسترسی "
                "اتریسا پیدا نشد.\n"
                "مطمئن شو اتریسا قبلاً به گروه یا کانال "
                "دسترسی داشته است."
            )
            return

        if not (
            target_dialog.is_group
            or target_dialog.is_channel
        ):
            await event.reply(
                "❌ این شناسه متعلق به گروه یا کانال نیست."
            )
            return

        channel = target_dialog.entity

    except Exception as exc:
        await event.reply(
            "❌ دریافت فهرست گفت‌وگوها ناموفق بود.\n"
            f"جزئیات: {exc}"
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
            filter=types.InputMessagesFilterGif(),
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

    print("✅ GIF Grabber - گیف به Saved GIFs اضافه شد.")
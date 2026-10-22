from typing import TYPE_CHECKING
import ast
import re

from splusthon.tl.functions.messages import SendMediaRequest
from splusthon import events
from splusthon.tl.functions.messages import SaveGifRequest,GetSavedGifsRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from core.decorators import command, on_event

from . import memory, sender

if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


MAX_GIFS_PER_COMMAND = 2000000
MAX_SEND_GIFS_PER_COMMAND = 5000
# حداکثر تعداد درخواست‌های حذف هم‌زمان
GIF_DELETE_CONCURRENCY = 5


@command(
    name="آمار گیف ها",
    permission="owner",
    chat_type="all",
    description="تعداد کل گیف‌ها و ۱۰ تگ پرتکرار را نمایش می‌دهد.",
    native_name="gif_stats",
)
async def gif_stats(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    try:
        total_gifs, top_tags = await memory.get_gif_statistics(
            self.db,
            tag_limit=10,
        )

    except Exception as exc:
        print(
            "❌ GIF Grabber - "
            f"دریافت آمار گیف‌ها ناموفق بود: {exc}"
        )

        await event.reply(
            "❌ دریافت آمار گیف‌ها ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}`"
        )
        return

    lines = [
        "📊 آمار بانک مرکزی گیف‌ها",
        "",
        f"🎞️ تعداد کل گیف‌ها: {total_gifs:,}",
        "",
        "🏷️ ۱۰ تگ پرتکرار:",
    ]

    if not top_tags:
        lines.append("هنوز هیچ تگی ثبت نشده است.")

    else:
        for index, row in enumerate(top_tags, start=1):
            tag = str(row["tag"]).replace("\n", " ").replace("\r", " ")
            count = int(row["gif_count"])

            lines.append(
                f"{index}. {tag} — {count:,} گیف"
            )

    await event.reply("\n".join(lines))



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


    args_text = getattr(event, "args_text", "").strip()

    match = re.fullmatch(
        r"(\d+)\s+(-?\d+)(?:\s+(.+))?",
        args_text,
        re.DOTALL,
    )

    if not match:
        await event.reply(
            "❌ قالب دستور نامعتبر است.\n"
            "مثال بدون تگ:\n"
            "!دریافت 100 -100\n\n"
            "مثال همراه تگ:\n"
            '!دریافت 100 -100 ["بانمک", "کیوت", "نینی"]'
        )
        return

    try:
        requested_count = int(match.group(1))
        channel_id = int(match.group(2))
    except (TypeError, ValueError):
        await event.reply(
            "❌ تعداد گیف‌ها و شناسهٔ کانال باید عدد باشند."
        )
        return

    tags = None
    tags_text = match.group(3)

    if tags_text:
        try:
            parsed_tags = ast.literal_eval(tags_text)
        except (ValueError, SyntaxError):
            await event.reply(
                "❌ تگ‌ها باید به‌شکل یک فهرست معتبر باشند.\n"
                'مثال: ["بانمک", "کیوت", "نینی"]'
            )
            return

        if (
            not isinstance(parsed_tags, list)
            or any(not isinstance(tag, str) for tag in parsed_tags)
        ):
            await event.reply(
                "❌ تگ‌ها باید فهرستی از رشته‌ها باشند.\n"
                'مثال: ["بانمک", "کیوت", "نینی"]'
            )
            return

        tags = list(dict.fromkeys(
            tag.strip()
            for tag in parsed_tags
            if tag.strip()
        ))


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

        try:
            await memory.initialize(self.db)
        
        except Exception as exc:
            await event.reply(
                "❌ آماده‌سازی بانک مرکزی گیف‌ها ناموفق بود.\n"
                f"جزئیات: {exc}"
            )
            return

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

    collected_count = 0
    duplicate_count = 0
    failed_count = 0
    scanned_count = 0
    processed_count = 0

    seen_gif_keys = set()
    stopped_reason = None


    # --------------------------------------------------
    # Scan GIF history page by page, newest to oldest
    # Keep the server-side GIF filter enabled.
    # --------------------------------------------------

    import asyncio

    PAGE_SIZE = 100
    offset_id = 0
    stop_requested = False

    while processed_count < target_count:
        page = []

        try:
            async for message in self.client.iter_messages(
                channel,
                limit=PAGE_SIZE,
                offset_id=offset_id,
                filter=types.InputMessagesFilterGif(),
            ):
                page.append(message)

        except FloodWaitError as exc:
            wait_seconds = getattr(exc, "seconds", None)

            stopped_reason = (
                "محدودیت درخواست هنگام دریافت صفحهٔ بعدی"
                + (
                    f"؛ زمان انتظار: {wait_seconds} ثانیه"
                    if wait_seconds is not None
                    else ""
                )
            )

            print(
                "⚠️ GIF Grabber - "
                f"FloodWait هنگام پیمایش تاریخچه: {exc}"
            )
            break

        except Exception as exc:
            stopped_reason = (
                f"خطا هنگام دریافت صفحهٔ تاریخچه: {exc}"
            )

            print(
                "❌ GIF Grabber - "
                f"دریافت صفحهٔ تاریخچه ناموفق بود: {exc}"
            )
            break

        # هیچ نتیجهٔ دیگری باقی نمانده است.
        if not page:
            break

        # در حالت پیش‌فرض، پیام‌ها از جدید به قدیم هستند.
        # شناسهٔ آخرین پیام، نقطهٔ شروع صفحهٔ بعدی است.
        next_offset_id = page[-1].id

        # جلوگیری از حلقهٔ بی‌نهایت در صورت تکرار صفحه.
        if offset_id and next_offset_id >= offset_id:
            stopped_reason = (
                "شناسهٔ صفحهٔ بعدی پیشروی نکرد؛ "
                "برای جلوگیری از حلقهٔ تکراری متوقف شد."
            )
            print(f"⚠️ GIF Grabber - {stopped_reason}")
            break

        offset_id = next_offset_id

        for message in page:
            scanned_count += 1
            
            gif = message.gif

            if gif is None:
                continue

            document_id = getattr(gif, "id", None)
            access_hash = getattr(gif, "access_hash", None)

            if document_id is None or access_hash is None:
                failed_count += 1
                print(
                    "⚠️ GIF Grabber - "
                    "شناسه یا access_hash گیف موجود نیست."
                )
                continue

            gif_key = (document_id, access_hash)

            # جلوگیری از بررسی تکراری یک گیف در همین اجرا
            if gif_key in seen_gif_keys:
                continue


            seen_gif_keys.add(gif_key)
            processed_count += 1

            try:
                is_new = await memory.remember_gif(
                    self.db,
                    document_id,
                    access_hash,
                    tags=tags,
                )

            except Exception as exc:
                failed_count += 1
                print(
                    "❌ GIF Grabber - ثبت گیف "
                    f"{document_id} ناموفق بود: {exc}"
                )

            else:
                if is_new:
                    collected_count += 1

                    print(
                        "✅ GIF Grabber - گیف جدید ثبت شد: "
                        f"{document_id}"
                    )
                else:
                    duplicate_count += 1

                    print(
                        "♻️ GIF Grabber - گیف تکراری بررسی شد "
                        "و تگ‌های جدید احتمالی ثبت شدند: "
                        f"{document_id}"
                    )

            if processed_count >= target_count:
                stop_requested = True
                break


        if stop_requested:
            break

        # فاصلهٔ کوتاه بین درخواست صفحه‌های تاریخچه
        await asyncio.sleep(1)

    # --------------------------------------------------
    # Final report
    # --------------------------------------------------


    result_lines = [
        "📥 عملیات جمع‌آوری گیف تمام شد.",
        f"🆕 رکوردهای جدید: {collected_count}",
        f"♻️ گیف‌های تکراری: {duplicate_count}",
        f"❌ خطاهای ثبت: {failed_count}",
        f"🔎 پیام‌های بررسی‌شده: {scanned_count}",
        f"🏷️ گیف‌های پردازش‌شده: {processed_count}",
    ]

    if requested_count > MAX_GIFS_PER_COMMAND:
        result_lines.append(
            f"ℹ️ سقف هر اجرا {MAX_GIFS_PER_COMMAND} گیف است."
        )

    if stopped_reason:
        result_lines.append(
            f"⚠️ علت توقف: {stopped_reason}"
        )
    elif processed_count < target_count:
        result_lines.append(
            "ℹ️ تاریخچه تمام شد یا گیف جدید دیگری پیدا نشد."
        )

    await event.reply("\n".join(result_lines))


@command(
    name="ارسال",
    permission="owner",
    chat_type="all",
    description="ارسال گیف به کاربر، گروه یا کانال؛ با پشتیبانی از تگ و زمان‌بندی.",
    native_name="send_gifs",
)
async def send_gifs(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    args_text = getattr(
        event,
        "args_text",
        "",
    ).strip()

    match = re.fullmatch(
        r"\s*(\d+)\s+(-?\d+)(?:\s+(.*?))?\s*",
        args_text,
        re.DOTALL,
    )

    if not match:
        await event.reply(
            "❌ قالب دستور نامعتبر است.\n"
            "نمونه‌ها:\n"
            "`!ارسال 50 49245702`\n"
            "`!ارسال 50 -100123 عاشقانه`\n"
            '`!ارسال 50 -100123 ["عاشقانه", "کیوت"] 2 ثانیه`\n'
            "`!ارسال 50 -100123 1 دقیقه`"
        )
        return

    requested_count = int(match.group(1))
    target_id = int(match.group(2))
    tail = (match.group(3) or "").strip()

    if requested_count <= 0 or target_id == 0:
        await event.reply(
            "❌ تعداد باید مثبت باشد و شناسهٔ مقصد نمی‌تواند صفر باشد."
        )
        return

    # استخراج فاصلهٔ زمانی از انتهای دستور
    interval_seconds = 0

    interval_match = re.search(
        r"(\d+)\s*(ثانیه(?:‌ها|ها| ها)?|دقیقه(?:‌ها|ها| ها)?|دیقه|ساعت|روز)\s*$",
        tail,
    )

    if interval_match:
        interval_value = int(
            interval_match.group(1)
        )

        unit = (
            interval_match.group(2)
            .replace("\u200c", "")
            .replace(" ", "")
        )

        if interval_value <= 0:
            await event.reply(
                "❌ فاصلهٔ زمانی باید بیشتر از صفر باشد."
            )
            return

        if unit.startswith("ثانیه"):
            multiplier = 1

        elif unit.startswith("دقیقه") or unit == "دیقه":
            multiplier = 60

        elif unit == "ساعت":
            multiplier = 60 * 60

        else:
            multiplier = 24 * 60 * 60

        interval_seconds = interval_value * multiplier

        # عبارت زمانی از انتهای دستور جدا می‌شود تا باقی‌مانده
        # برای استخراج تگ‌ها استفاده شود.
        tail = tail[:interval_match.start()].strip()

    # استخراج تگ‌ها
    tags = None

    if tail:
        if tail.startswith("["):
            try:
                parsed_tags = ast.literal_eval(tail)

            except (ValueError, SyntaxError):
                await event.reply(
                    "❌ فهرست تگ‌ها معتبر نیست.\n"
                    'مثال: `["عاشقانه", "کیوت"]`'
                )
                return

            if (
                not isinstance(parsed_tags, list)
                or any(
                    not isinstance(tag, str)
                    for tag in parsed_tags
                )
            ):
                await event.reply(
                    "❌ تگ‌ها باید فهرستی از متن باشند."
                )
                return

            tags = list(dict.fromkeys(
                tag.strip()
                for tag in parsed_tags
                if tag.strip()
            ))

            if not tags:
                await event.reply(
                    "❌ فهرست تگ‌ها خالی است."
                )
                return

        else:
            # یک تگ متنی؛ برای چند تگ از فهرست استفاده کن.
            tags = [tail]

    target_count = min(
        requested_count,
        MAX_SEND_GIFS_PER_COMMAND,
    )

    try:
        gifs = await memory.get_random_gifs(
            self.db,
            target_count,
            tags=tags,
        )

    except Exception as exc:
        await event.reply(
            "❌ خواندن بانک مرکزی گیف‌ها ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}: {exc}`"
        )
        return

    if not gifs:
        if tags:
            await event.reply(
                "ℹ️ گیفی با تمام تگ‌های انتخاب‌شده پیدا نشد.\n"
                "تگ‌ها باید دقیقاً با تگ‌های ثبت‌شده یکسان باشند."
            )
        else:
            await event.reply(
                "ℹ️ بانک مرکزی گیف‌ها خالی است."
            )
        return

    # تبدیل ردیف‌های دیتابیس به دادهٔ قابل ذخیره در JSON
    gifs_payload = [
        {
            "doc_id": int(gif["doc_id"]),
            "access_hash": int(gif["access_hash"]),
        }
        for gif in gifs
    ]

    try:
        notify_chat_id = int(
            getattr(event, "chat_id", 0) or 0
        )

        job_id = await sender.schedule_send_job(
            self,
            target_id=target_id,
            notify_chat_id=notify_chat_id,
            gifs=gifs_payload,
            interval_seconds=interval_seconds,
        )

    except Exception as exc:
        await event.reply(
            "❌ ساخت کار ارسال زمان‌بندی‌شده ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}: {exc}`"
        )
        return

    report_lines = [
        f"✅ کار ارسال گیف با شناسهٔ `{job_id}` شروع شد.",
        f"🎯 مقصد: `{target_id}`",
        f"🎞️ تعداد گیف انتخاب‌شده: {len(gifs_payload)}",
        (
            f"⏱️ فاصلهٔ بین ارسال‌ها: هر {interval_seconds} ثانیه"
            if interval_seconds
            else "⏱️ فاصلهٔ بین ارسال‌ها: بدون مکث عمدی"
        ),
        f"🏷️ تگ‌ها: {', '.join(tags) if tags else 'همهٔ گیف‌ها'}",
        f"برای لغو این کار: `!توقف_ارسال {job_id}`",
    ]

    if requested_count > MAX_SEND_GIFS_PER_COMMAND:
        report_lines.append(
            f"ℹ️ سقف هر اجرا {MAX_SEND_GIFS_PER_COMMAND} گیف است."
        )

    if len(gifs_payload) < target_count:
        report_lines.append(
            "ℹ️ تعداد گیف‌های واجد شرایط کمتر از تعداد درخواستی بود؛ "
            "تمام گیف‌های موجود در این مجموعه انتخاب شدند."
        )

    await event.reply(
        "\n".join(report_lines)
    )


@command(
    name="توقف_ارسال",
    permission="owner",
    chat_type="all",
    description="توقف یک کار ارسال گیف یا همهٔ کارهای فعال.",
    native_name="stop_gif_send",
)
async def stop_send_gifs(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    args = getattr(event, "args", [])

    if len(args) > 1:
        await event.reply(
            "❌ فقط یک شناسهٔ کار وارد کن.\n"
            "مثال: `!توقف_ارسال 12`\n"
            "برای توقف همهٔ ارسال‌ها، `!توقف_ارسال` را بدون آرگومان بفرست."
        )
        return

    job_id = None

    if args:
        try:
            job_id = int(args[0])

        except (TypeError, ValueError):
            await event.reply(
                "❌ شناسهٔ کار باید عدد باشد."
            )
            return

        if job_id <= 0:
            await event.reply(
                "❌ شناسهٔ کار باید مثبت باشد."
            )
            return

    try:
        stopped_ids = await sender.stop_send_jobs(
            self,
            job_id,
        )

    except Exception as exc:
        await event.reply(
            "❌ توقف ارسال ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}: {exc}`"
        )
        return

    if not stopped_ids:
        await event.reply(
            "ℹ️ کار فعالی با این شناسه پیدا نشد."
        )
        return

    if job_id is not None:
        await event.reply(
            f"🛑 ارسال گیف با شناسهٔ `{job_id}` متوقف شد."
        )
    else:
        await event.reply(
            "🛑 همهٔ ارسال‌های فعال متوقف شدند: "
            + ", ".join(
                f"`{value}`" for value in stopped_ids
            )
        )


@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    if event.document:
        print(event.document.id,"___access hash___",event.document.access_hash)
    
    if (
        event.is_group is not True
        and event.is_channel is not True
    ):
        return
    print('event recived')
    raw_text = (event.raw_text or "").strip()

    # --------------------------------------------------
    # TEST: send the document with ID 0
    # --------------------------------------------------

    if raw_text == "0":
        document_id = 144516515687941428
        access_hash = -1768943261643636478

    else:
        # Accept Document(id=..., access_hash=...)
        # or a message containing the two labelled values.
        match = re.search(
            r"\bid\s*=\s*(-?\d+)\s*,\s*"
            r"access_hash\s*=\s*(-?\d+)",
            raw_text,
            re.IGNORECASE,
        )

        if match:
            document_id = int(match.group(1))
            access_hash = int(match.group(2))

        elif re.fullmatch(
            r"\s*-?\d+\s+-?\d+\s*",
            raw_text,
        ):
            # Also accept exactly two space-separated integers.
            values = [
                int(value)
                for value in raw_text.split()
            ]
            document_id, access_hash = values

        else:
            document_id = None
            access_hash = None

    # --------------------------------------------------
    # Try sending the requested document
    # --------------------------------------------------

    if document_id is not None:
        saved_error = None

        # Method 1: look for the document in Saved GIFs.
        # This can provide a current file_reference.
        try:
            response = await self.client(
                GetSavedGifsRequest(hash=0)
            )

            gifs = getattr(response, "gifs", None) or []

            gif = next(
                (
                    item
                    for item in gifs
                    if getattr(item, "id", None) == document_id
                    and getattr(item, "access_hash", None)
                    == access_hash
                ),
                None,
            )

            if gif is not None:
                input_document = types.InputDocument(
                    id=gif.id,
                    access_hash=gif.access_hash,
                    file_reference=gif.file_reference,
                )

                await self.client(
                    SendMediaRequest(
                        peer=event.chat_id,
                        media=types.InputMediaDocument(
                            id=input_document,
                        ),
                        message="",
                    )
                )

                print(
                    "✅ GIF Grabber - سند با مرجع "
                    "موجود در Saved GIFs ارسال شد: "
                    f"{document_id}"
                )
                return

        except Exception as exc:
            saved_error = str(exc)

            print(
                "⚠️ GIF Grabber - ارسال از Saved GIFs "
                f"موفق نبود: {exc}"
            )

        # Method 2: experimental direct access using
        # only document ID and access hash.
        try:
            input_document = types.InputDocument(
                id=document_id,
                access_hash=access_hash,
                file_reference=b"",
            )

            await self.client(
                SendMediaRequest(
                    peer=event.chat_id,
                    media=types.InputMediaDocument(
                        id=input_document,
                    ),
                    message="",
                )
            )

            print(
                "✅ GIF Grabber - ارسال مستقیم با "
                "file_reference خالی موفق بود: "
                f"{document_id}"
            )
            return

        except Exception as exc:
            print(
                "❌ GIF Grabber - ارسال مستقیم سند "
                f"{document_id} ناموفق بود: {exc}"
            )

            details = (
                f"\nخطای Saved GIFs: {saved_error}"
                if saved_error
                else ""
            )

            await event.reply(
                "❌ ارسال گیف ناموفق بود.\n"
                f"شناسه: {document_id}\n"
                f"خطای روش مستقیم: {exc}"
                f"{details}"
            )
            return

    # --------------------------------------------------
    # Existing behavior: save incoming GIFs
    # --------------------------------------------------

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

    print(
        "✅ GIF Grabber - "
        "گیف به Saved GIFs اضافه شد."
    )

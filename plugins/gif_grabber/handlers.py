from typing import TYPE_CHECKING
import ast
import re

from splusthon.tl.functions.messages import SendMediaRequest
from splusthon import events
from splusthon.tl.functions.messages import SaveGifRequest,GetSavedGifsRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from core.decorators import command, on_event

from . import memory

if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


MAX_GIFS_PER_COMMAND = 200
MAX_SEND_GIFS_PER_COMMAND = 5000
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
    description="گیف‌های تصادفی بانک مرکزی را برای یک UID می‌فرستد.",
    native_name="send_gifs",
)
async def send_gifs(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    args = getattr(event, "args", [])

    if len(args) != 2:
        await event.reply(
            "❌ تعداد گیف و UID مقصد را وارد کن.\n"
            "مثال:\n"
            + self.command_usage(
                event.command,
                "1 <UID>",
                event=event,
            )
        )
        return

    try:
        requested_count = int(args[0])
        target_uid = int(args[1])
    except (TypeError, ValueError):
        await event.reply(
            "❌ تعداد گیف و UID باید عدد باشند."
        )
        return

    if requested_count <= 0 or target_uid <= 0:
        await event.reply(
            "❌ تعداد و UID باید بزرگ‌تر از صفر باشند."
        )
        return

    target_count = min(
        requested_count,
        MAX_SEND_GIFS_PER_COMMAND,
    )

    try:
        gifs = await memory.get_random_gifs(
            self.db,
            target_count,
        )
    except Exception as exc:
        await event.reply(
            "❌ خواندن بانک مرکزی گیف‌ها ناموفق بود.\n"
            f"جزئیات: {exc}"
        )
        return

    if not gifs:
        await event.reply(
            "ℹ️ بانک مرکزی گیف‌ها خالی است."
        )
        return

    # تشخیص UID خود یوزربات برای ارسال به Saved Messages
    try:
        me = await self.client.get_me()
        my_uid = getattr(me, "id", None)

        if my_uid is None:
            raise RuntimeError(
                "شناسهٔ حساب فعلی قابل تشخیص نیست."
            )

        if int(my_uid) == target_uid:
            target_peer = "me"
        else:
            target_peer = await self.client.get_input_entity(
                target_uid
            )

    except Exception as exc:
        await event.reply(
            "❌ تشخیص حساب مقصد ناموفق بود.\n"
            f"جزئیات: {exc}"
        )
        return

    sent_count = 0
    failed_count = 0

    for gif in gifs:
        document_id = int(gif["doc_id"])
        access_hash = int(gif["access_hash"])

        try:
            input_document = types.InputDocument(
                id=document_id,
                access_hash=access_hash,
                file_reference=b"",
            )

            await self.client(
                SendMediaRequest(
                    peer=target_peer,
                    media=types.InputMediaDocument(
                        id=input_document,
                    ),
                    message="",
                )
            )

            sent_count += 1

            print(
                "✅ GIF Grabber - گیف ارسال شد: "
                f"{document_id} → {target_uid}"
            )

        except Exception as exc:
            failed_count += 1

            print(
                "❌ GIF Grabber - ارسال گیف "
                f"{document_id} به {target_uid} ناموفق بود: "
                f"{exc}"
            )

    result_lines = [
        "📤 عملیات ارسال گیف تمام شد.",
        f"🎯 UID مقصد: {target_uid}",
        f"✅ ارسال موفق: {sent_count}",
        f"❌ ارسال ناموفق: {failed_count}",
    ]

    if requested_count > MAX_SEND_GIFS_PER_COMMAND:
        result_lines.append(
            f"ℹ️ سقف هر اجرا "
            f"{MAX_SEND_GIFS_PER_COMMAND} گیف است."
        )

    await event.reply("\n".join(result_lines))






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

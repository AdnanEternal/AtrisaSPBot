from typing import TYPE_CHECKING
import ast
import re
import asyncio
from urllib.parse import parse_qs, unquote, urlsplit

from splusthon.tl.functions.messages import SendMediaRequest
from splusthon import events
from splusthon.tl.functions.messages import SaveGifRequest,GetSavedGifsRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError


from core.permissions import is_owner
from core.decorators import command, on_event

from . import memory, sender

if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


MAX_GIFS_PER_COMMAND = 9999999
MAX_SEND_GIFS_PER_COMMAND = 9999999
# حداکثر تعداد درخواست‌های حذف هم‌زمان
GIF_DELETE_CONCURRENCY = 5



def _parse_dict_command(
    args_text: str,
    *,
    required_keys: set[str],
    allowed_keys: set[str],
) -> dict:
    """خواندن و اعتبارسنجی دیکشنری ورودی دستور."""

    try:
        data = ast.literal_eval(args_text.strip())
    except (ValueError, SyntaxError):
        raise ValueError(
            'ورودی باید دیکشنری معتبر باشد؛ مثال: '
            '{"value": 25, "id": -100, "tags": ["لاو"]}'
        )

    if not isinstance(data, dict):
        raise ValueError("ورودی باید یک دیکشنری پایتونی باشد.")

    unknown_keys = set(data) - allowed_keys
    if unknown_keys:
        raise ValueError(
            "کلیدهای ناشناخته: "
            + ", ".join(map(str, unknown_keys))
        )

    missing_keys = required_keys - set(data)
    if missing_keys:
        raise ValueError(
            "کلیدهای ضروری وارد نشده‌اند: "
            + ", ".join(sorted(missing_keys))
        )

    if any(not isinstance(key, str) for key in data):
        raise ValueError("نام تمام کلیدها باید رشته باشد.")

    return data


def _parse_gif_tags(value) -> list[str] | None:
    """اعتبارسنجی تگ‌ها؛ نبودن tags یعنی بدون فیلتر تگ."""

    if value is None:
        return None

    if (
        not isinstance(value, list)
        or any(not isinstance(tag, str) for tag in value)
    ):
        raise ValueError(
            'کلید tags باید فهرستی از متن باشد؛ مثال: ["لاو"]'
        )

    tags = list(dict.fromkeys(
        tag.strip()
        for tag in value
        if tag.strip()
    ))

    if not tags:
        raise ValueError(
            "فهرست tags نمی‌تواند خالی باشد؛ "
            "برای ارسال بدون فیلتر تگ، کلید tags را حذف کن."
        )

    return tags


def _parse_gif_filter(value) -> list[str] | None:
    """اعتبارسنجی فهرست کلمات کلیدی فیلتر متن پیام‌ها."""

    if value is None:
        return None

    if (
        not isinstance(value, list)
        or any(not isinstance(keyword, str) for keyword in value)
    ):
        raise ValueError(
            'کلید filter باید فهرستی از متن باشد؛ '
            'مثال: ["#Baby", "#Cute"]'
        )

    keywords = list(dict.fromkeys(
        keyword.strip()
        for keyword in value
        if keyword.strip()
    ))

    if not keywords:
        raise ValueError(
            "فهرست filter نمی‌تواند خالی باشد؛ "
            "برای دریافت بدون فیلتر متن، کلید filter را حذف کن."
        )

    return keywords



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


    args_text = getattr(
        event,
        "args_text",
        "",
    ).strip()

    try:
        data = _parse_dict_command(
            args_text,
            required_keys={"value", "id"},
            allowed_keys={"value", "id", "tags", "filter"},
        )

        requested_count = data["value"]
        channel_id = data["id"]
        tags = _parse_gif_tags(data.get("tags"))
        filter_keywords = _parse_gif_filter(data.get("filter"))

        if (
            isinstance(requested_count, bool)
            or not isinstance(requested_count, int)
            or requested_count <= 0
        ):
            raise ValueError(
                "value باید یک عدد صحیح مثبت باشد."
            )

        if (
            isinstance(channel_id, bool)
            or not isinstance(channel_id, int)
            or channel_id == 0
        ):
            raise ValueError(
                "id باید شناسهٔ عددی و غیرصفر کانال باشد."
            )

    except (ValueError, TypeError, KeyError) as exc:
        await event.reply(
            "❌ ورودی دستور دریافت معتبر نیست.\n"
            f"جزئیات: {exc}\n\n"
            "نمونه بدون تگ:\n"
            '`!دریافت {"value": 100, "id": -1000025170952}`\n\n'
            "نمونه همراه تگ:\n"
            '`!دریافت {"value": 100, "id": -1000025170952, '
            '"tags": ["لاو", "کیوت"]}`'
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

            # بررسی کلمات کلیدی در متن یا کپشن پیام
            if filter_keywords:
                message_text = (
                    getattr(message, "message", None)
                    or getattr(message, "text", None)
                    or getattr(message, "raw_text", None)
                    or ""
                )

                message_text = str(message_text).casefold()

                # وجود حداقل یکی از کلمات برای پذیرش پیام کافی است.
                if not any(
                    keyword.casefold() in message_text
                    for keyword in filter_keywords
                ):
                    continue

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


def _get_send_lock(
    self,
    target_id: int,
) -> asyncio.Lock:
    """قفل مستقل برای هماهنگ‌کردن انتخاب و رزرو گیف‌های هر مقصد."""

    target_id = int(target_id)

    locks = getattr(
        self,
        "_gif_send_locks",
        None,
    )

    if locks is None:
        locks = {}
        self._gif_send_locks = locks

    lock = locks.get(target_id)

    if lock is None:
        lock = asyncio.Lock()
        locks[target_id] = lock

    return lock


@command(
    name="اجازه_تکرار_گیف",
    permission="owner",
    chat_type="all",
    description="فعال یا غیرفعال کردن ارسال گیف تکراری برای یک مقصد.",
    native_name="set_gif_repeats",
)
async def set_gif_repeats(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    args_text = getattr(
        event,
        "args_text",
        "",
    ).strip()

    match = re.fullmatch(
        r"(-?\d+)\s+(روشن|خاموش|فعال|غیرفعال|on|off)",
        args_text,
        re.IGNORECASE,
    )

    if not match:
        await event.reply(
            "❌ قالب دستور نامعتبر است.\n"
            "برای ممنوع‌کردن گیف تکراری:\n"
            "`!اجازه_تکرار_گیف -100123 خاموش`\n\n"
            "برای مجازکردن آن:\n"
            "`!اجازه_تکرار_گیف -100123 روشن`"
        )
        return

    try:
        target_id = int(match.group(1))

    except (TypeError, ValueError):
        await event.reply(
            "❌ شناسهٔ مقصد معتبر نیست."
        )
        return

    if target_id == 0:
        await event.reply(
            "❌ شناسهٔ مقصد نمی‌تواند صفر باشد."
        )
        return

    state = match.group(2).lower()

    allow_repeats = state in {
        "روشن",
        "فعال",
        "on",
    }

    try:
        # تغییر تنظیم و انتخاب گیف برای همان مقصد
        # نباید هم‌زمان و با تنظیمات متفاوت انجام شود.
        async with _get_send_lock(self, target_id):
            await memory.set_chat_repeats(
                self.db,
                target_id,
                allow_repeats,
            )

    except Exception as exc:
        await event.reply(
            "❌ تغییر تنظیم تکرار گیف ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}: {exc}`"
        )
        return

    status = (
        "مجاز شد"
        if allow_repeats
        else "ممنوع شد"
    )

    await event.reply(
        f"✅ ارسال گیف تکراری برای مقصد `{target_id}` {status}."
    )


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

    try:
        data = _parse_dict_command(
            args_text,
            required_keys={"value", "id"},
            allowed_keys={
                "value",
                "id",
                "delay",
                "tags",
                "caption",
            },
        )

        requested_count = data["value"]
        target_id = data["id"]
        delay = data.get("delay", 0)
        tags = _parse_gif_tags(data.get("tags"))
        caption = data.get("caption", "")

        if not isinstance(caption, str):
            raise ValueError(
                "caption باید متن باشد."
            )

        if (
            isinstance(requested_count, bool)
            or not isinstance(requested_count, int)
            or requested_count <= 0
        ):
            raise ValueError(
                "value باید یک عدد صحیح مثبت باشد."
            )

        if (
            isinstance(target_id, bool)
            or not isinstance(target_id, int)
            or target_id == 0
        ):
            raise ValueError(
                "id باید شناسهٔ عددی و غیرصفر مقصد باشد."
            )

        if (
            isinstance(delay, bool)
            or not isinstance(delay, int)
            or delay < 0
        ):
            raise ValueError(
                "delay باید عدد صحیح صفر یا بزرگ‌تر باشد."
            )

    except (ValueError, TypeError, KeyError) as exc:
        await event.reply(
            "❌ ورودی دستور ارسال معتبر نیست.\n"
            f"جزئیات: {exc}\n\n"
            "نمونه:\n"
            '`!ارسال {"value": 25, "id": -1000025170952, '
            '"delay": 2, "tags": ["لاو"]}`'
        )
        return

    interval_seconds = delay

    target_count = min(
        requested_count,
        MAX_SEND_GIFS_PER_COMMAND,
    )



    

    no_gifs_message = None
    gifs_payload = []
    job_id = None

    try:
        # انتخاب گیف و ثبت کار ارسال برای یک مقصد
        # پشت سر هم انجام می‌شوند تا دو دستور هم‌زمان
        # یک گیف را به‌عنوان گیف جدید انتخاب نکنند.
        async with _get_send_lock(self, target_id):

            allow_repeats = await memory.get_chat_repeats(
                self.db,
                target_id,
            )

            if allow_repeats:
                # رفتار قبلی: انتخاب تصادفی بدون محدودیت سابقه
                gifs = await memory.get_gifs(
                    self.db,
                    target_count,
                    tags=tags,
                )

            else:
                # گیف‌های رزروشده در ارسال‌های فعال این اجرا
                reserved_gifs = sender.get_reserved_gifs(
                    self,
                    target_id,
                )

                # انتخاب مستقیم گیف‌های ارسال‌نشده
                gifs = await memory.get_gifs_for_chat(
                    self.db,
                    target_count,
                    chat_id=target_id,
                    tags=tags,
                    reserved_gifs=reserved_gifs,
                )

            if not gifs:
                if not allow_repeats:
                    no_gifs_message = (
                        "ℹ️ گیف واجد شرایطی برای ارسال باقی نمانده است.\n"
                        "ممکن است همهٔ گیف‌های مطابق تگ‌ها قبلاً "
                        "در این مقصد ارسال شده باشند یا برای ارسال "
                        "فعال دیگری رزرو شده باشند."
                    )

                elif tags:
                    no_gifs_message = (
                        "ℹ️ گیفی با تمام تگ‌های انتخاب‌شده پیدا نشد.\n"
                        "تگ‌ها باید دقیقاً با تگ‌های ثبت‌شده یکسان باشند."
                    )

                else:
                    no_gifs_message = (
                        "ℹ️ بانک مرکزی گیف‌ها خالی است."
                    )

            else:
                # تبدیل ردیف‌های دیتابیس به دادهٔ قابل ذخیره در JSON
                gifs_payload = [
                    {
                        "doc_id": int(gif["doc_id"]),
                        "access_hash": int(gif["access_hash"]),
                    }
                    for gif in gifs
                ]

                notify_chat_id = int(
                    getattr(event, "chat_id", 0) or 0
                )

                # ثبت کار در دیتابیس و شروع ارسال
                # قبل از آزادشدن قفل انجام می‌شود.
                job_id = await sender.start_send_job(
                    self,
                    target_id=target_id,
                    notify_chat_id=notify_chat_id,
                    gifs=gifs_payload,
                    interval_seconds=interval_seconds,
                    caption=caption,
                )

    except Exception as exc:
        await event.reply(
            "❌ ساخت کار ارسال زمان‌بندی‌شده ناموفق بود.\n"
            f"جزئیات: `{type(exc).__name__}: {exc}`"
        )
        return

    if no_gifs_message:
        await event.reply(no_gifs_message)
        return

    if job_id is None:
        await event.reply(
            "❌ کار ارسال گیف ایجاد نشد."
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


_SOROUSH_LINK_PATTERN = re.compile(
    r"""https?://[^\s<>"']+|
        (?:splus|soroush)://[^\s<>"']+|
        (?<![\w@])(?:www\.)?(?:splus\.ir|web\.splus\.ir|sapp\.ir|soroush-app\.ir)/[^\s<>"']+
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SOROUSH_HOSTS = {
    "splus.ir",
    "www.splus.ir",
    "web.splus.ir",
    "sapp.ir",
    "www.sapp.ir",
    "soroush-app.ir",
    "www.soroush-app.ir",
}

_ROUTE_SEGMENTS = {
    "resolve",
    "join",
    "joinchat",
    "c",
    "p",
    "post",
    "message",
    "messages",
    "channel",
    "channels",
    "group",
    "groups",
    "chat",
    "chats",
    "open",
    "view",
}

_MESSAGE_QUERY_KEYS = (
    "message_id",
    "messageid",
    "msg_id",
    "msgid",
    "mid",
    "post_id",
    "postid",
    "post",
    "msg",
    "message",
)

_CHAT_QUERY_KEYS = (
    "username",
    "domain",
    "channel",
    "channel_id",
    "group",
    "group_id",
    "chat",
    "chat_id",
    "peer",
)


def _find_soroush_link(text: str) -> str | None:
    """پیداکردن نخستین لینک معتبر سروش‌پلاس در متن."""

    for match in _SOROUSH_LINK_PATTERN.finditer(text or ""):
        link = match.group(0).rstrip(
            ".,;!?)]}،؛»"
        )

        # لینک‌های بدون scheme را به URL معمولی تبدیل کن.
        if not re.match(
            r"^[a-z][a-z0-9+.-]*://",
            link,
            re.IGNORECASE,
        ):
            link = "https://" + link

        try:
            parsed = urlsplit(link)
        except ValueError:
            continue

        scheme = parsed.scheme.casefold()

        if scheme in {"splus", "soroush"}:
            return link

        if (
            scheme in {"http", "https"}
            and (parsed.hostname or "").casefold() in _SOROUSH_HOSTS
        ):
            return link

    return None


def _parse_soroush_message_link(
    link: str,
) -> tuple[str, int] | None:
    """
    استخراج مرجع گفتگو و شناسه پیام از لینک.

    خروجی: (chat_ref, message_id)
    """

    try:
        parsed = urlsplit(link)
    except ValueError:
        return None

    scheme = parsed.scheme.casefold()

    if scheme in {"http", "https"}:
        if (parsed.hostname or "").casefold() not in _SOROUSH_HOSTS:
            return None

    elif scheme not in {"splus", "soroush"}:
        return None

    path_parts = [
        unquote(part).strip()
        for part in parsed.path.split("/")
        if part.strip()
    ]

    query = {
        key.casefold(): values
        for key, values in parse_qs(parsed.query).items()
    }

    def query_value(keys):
        for key in keys:
            values = query.get(key)

            if values and str(values[0]).strip():
                return str(values[0]).strip()

        return None

    # ۱) ابتدا شناسه‌ای را که صریحاً در query به پیام مربوط است پیدا کن.
    message_id = None
    message_path_index = None

    for key in _MESSAGE_QUERY_KEYS:
        value = query_value((key,))

        if value and value.isdigit() and int(value) > 0:
            message_id = int(value)
            break

    # ۲) اگر شناسه در query نبود، آخرین بخش عددی مسیر را بررسی کن.
    if message_id is None:
        for index in range(len(path_parts) - 1, -1, -1):
            value = path_parts[index]

            if not value.isdigit() or int(value) <= 0:
                continue

            # در URL وب، یک بخش عددی تنها ممکن است شناسه گفتگو باشد.
            # برای پیام باید پیش از آن مرجع گفتگو یا مسیر مناسب وجود داشته باشد.
            custom_host = (
                scheme in {"splus", "soroush"}
                and parsed.netloc.casefold() not in _ROUTE_SEGMENTS
            )

            if (
                index > 0
                or custom_host
                or query_value(_CHAT_QUERY_KEYS)
            ):
                message_id = int(value)
                message_path_index = index
                break

    # ۳) پشتیبانی از پارامتر عمومی id در قالب‌هایی که از آن استفاده می‌کنند.
    if message_id is None:
        value = query_value(("id",))

        if value and value.isdigit() and int(value) > 0:
            message_id = int(value)

    if message_id is None:
        return None

    # مرجع گفتگو ممکن است جداگانه در query مشخص شده باشد.
    chat_ref = query_value(_CHAT_QUERY_KEYS)

    # اگر شناسه پیام از مسیر آمده، قسمت‌های بعد از آن متعلق به پیام‌اند.
    if message_path_index is not None:
        candidate_parts = path_parts[:message_path_index]
    else:
        candidate_parts = path_parts

    # حذف اجزای کنترلی مسیر، مانند /c/ و /message/.
    candidate_parts = [
        part
        for part in candidate_parts
        if part.casefold() not in _ROUTE_SEGMENTS
    ]

    if not chat_ref and candidate_parts:
        chat_ref = candidate_parts[-1]

    # پشتیبانی از URIهایی مانند splus://username/123
    if not chat_ref and scheme in {"splus", "soroush"}:
        host_ref = unquote(parsed.netloc).strip()

        if host_ref.casefold() not in _ROUTE_SEGMENTS:
            chat_ref = host_ref

    if not chat_ref:
        return None

    chat_ref = chat_ref.strip().lstrip("@")

    if not chat_ref:
        return None

    return chat_ref, message_id


def _dialog_matches_chat_ref(
    dialog,
    chat_ref: str,
) -> bool:
    """بررسی تطبیق لینک با یک گروه یا کانال در دسترس."""

    if not (
        getattr(dialog, "is_group", False)
        or getattr(dialog, "is_channel", False)
    ):
        return False

    entity = getattr(dialog, "entity", None)

    if entity is None:
        return False

    entity_type = type(entity).__name__.casefold()

    # گفتگوهای ممنوع‌شده یا ترک‌شده را عضوِ قابل‌دسترسی حساب نکن.
    if (
        "forbidden" in entity_type
        or getattr(entity, "left", False)
        or getattr(entity, "kicked", False)
    ):
        return False

    wanted = str(chat_ref).strip().lstrip("@").casefold()

    username = getattr(entity, "username", None)

    if username and str(username).strip().lstrip("@").casefold() == wanted:
        return True

    # بعضی لینک‌ها به جای username از شناسه عددی استفاده می‌کنند.
    try:
        wanted_id = int(wanted)
    except (TypeError, ValueError):
        return False

    candidates = set()

    for value in (
        getattr(dialog, "id", None),
        getattr(entity, "id", None),
    ):
        if value is None:
            continue

        value = int(value)
        candidates.update({
            value,
            abs(value),
            -abs(value),
        })

    entity_id = getattr(entity, "id", None)

    if entity_id is not None:
        entity_id = abs(int(entity_id))

        # قالب رایج شناسه کانال
        candidates.add(-int(f"100{entity_id}"))

        # قالب شناسه‌ای که در کد فعلی پروژه هم استفاده شده
        candidates.add(-(1_000_000_000_000 + entity_id))

    return wanted_id in candidates


async def _reply_gif_ids_from_link(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
    chat_ref: str,
    message_id: int,
) -> None:
    """پیداکردن پیام لینک‌شده و پاسخ‌دادن با مشخصات گیف."""

    try:
        dialogs = await self.client.get_dialogs()
    except Exception as exc:
        print(
            "❌ GIF Grabber - دریافت گفتگوها برای بررسی لینک "
            f"ناموفق بود: {exc}"
        )
        await event.reply(
            "❌ نتونستم فهرست گفتگوهای اتریسا رو دریافت کنم."
        )
        return

    source_dialog = next(
        (
            dialog
            for dialog in dialogs
            if _dialog_matches_chat_ref(dialog, chat_ref)
        ),
        None,
    )

    if source_dialog is None:
        await event.reply(
            "❌ گفتگوی این لینک در گفتگوهای در دسترس اتریسا پیدا نشد.\n"
            "ممکنه اتریسا عضو اون گروه یا کانال نباشه، "
            "یا مرجع گفتگو در لینک قابل تشخیص نباشه."
        )
        return

    try:
        message = await self.client.get_messages(
            source_dialog.entity,
            ids=message_id,
        )
    except Exception as exc:
        print(
            "❌ GIF Grabber - دریافت پیام لینک‌شده ناموفق بود: "
            f"{exc}"
        )
        await event.reply(
            "❌ دریافت پیام لینک‌شده ناموفق بود.\n"
            f"خطا: `{type(exc).__name__}`"
        )
        return

    # بعضی شکل‌های خروجی ممکن است فهرستی باشند.
    if isinstance(message, (list, tuple)):
        message = next(
            (item for item in message if item is not None),
            None,
        )

    if message is None or not getattr(message, "id", None):
        await event.reply(
            "❌ این پیام پیدا نشد یا اتریسا اجازهٔ دسترسی به اون رو نداره."
        )
        return

    # در SPlusthon، gif فقط برای سندهایی برمی‌گردد که ویژگی گیف متحرک دارند.
    try:
        gif = getattr(message, "gif", None)
    except Exception as exc:
        print(
            "❌ GIF Grabber - بررسی نوع رسانه پیام ناموفق بود: "
            f"{exc}"
        )
        gif = None

    if gif is None:
        await event.reply(
            "ℹ️ پیام پیدا شد، اما به‌عنوان گیف شناسایی نشد."
        )
        return

    document_id = getattr(gif, "id", None)
    access_hash = getattr(gif, "access_hash", None)

    if document_id is None or access_hash is None:
        await event.reply(
            "❌ اطلاعات لازم برای ارسال گیف موجود نیست."
        )
        return

    document_id = int(document_id)
    access_hash = int(access_hash)

    # تلاش اول: استفاده از file_reference خود پیام مبدأ
    file_reference = (
        getattr(gif, "file_reference", None) or b""
    )

    attempts = [
        ("مرجع اصلی پیام", file_reference),
        ("مرجع خالی", b""),
    ]

    errors = []

    for attempt_number, (attempt_name, reference) in enumerate(
        attempts,
        start=1,
    ):
        try:
            input_document = types.InputDocument(
                id=document_id,
                access_hash=access_hash,
                file_reference=reference,
            )

            await self.client(
                SendMediaRequest(
                    peer=event.chat_id,
                    media=types.InputMediaDocument(
                        id=input_document,
                    ),
                    message="",
                    reply_to=types.InputReplyToMessage(
                        event.id
                    ),
                )
            )

            print(
                "✅ GIF Grabber - ارسال گیف پیام لینک‌شده موفق بود؛ "
                f"شناسهٔ سند: {document_id}، "
                f"تلاش: {attempt_number}، "
                f"روش: {attempt_name}"
            )
            return

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            error_text = (
                f"{type(exc).__name__}: {exc}"
            )
            errors.append(
                f"تلاش {attempt_number} ({attempt_name}): "
                f"{error_text}"
            )

            print(
                "⚠️ GIF Grabber - ارسال گیف ناموفق بود؛ "
                f"شناسهٔ سند: {document_id}، "
                f"تلاش: {attempt_number}، "
                f"روش: {attempt_name}، "
                f"خطا: {error_text}"
            )

    # هر دو روش شکست خوردند.
    await event.reply(
        "❌ ارسال گیف ناموفق بود؛ هر دو تلاش شکست خوردند.\n\n"
        + "\n".join(errors)
    )

@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    raw_text = (event.raw_text or "").strip()

    # استخراج اطلاعات پیام لینک‌شده فقط برای مالک ربات
    if is_owner(getattr(event, "sender_id", None)):
        link = _find_soroush_link(raw_text)

        if link is not None:
            parsed_link = _parse_soroush_message_link(link)

            if parsed_link is None:
                await event.reply(
                    "❌ لینک سروش‌پلاس شناسایی شد، "
                    "اما شناسهٔ پیام یا گفتگو از قالب آن استخراج نشد.\n"
                    "لینک مستقیم خود پیام را بفرست، نه لینک صفحهٔ گفتگو."
                )
                return

            chat_ref, message_id = parsed_link

            await _reply_gif_ids_from_link(
                self,
                event,
                chat_ref,
                message_id,
            )
            return


    if (
        event.is_group is not True
        and event.is_channel is not True
    ):
        return


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

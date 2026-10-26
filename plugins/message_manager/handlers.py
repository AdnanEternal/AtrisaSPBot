import asyncio

from . import memory
from typing import TYPE_CHECKING

from splusthon import events,functions
from splusthon.errors import FloodWaitError, PeerFloodError

from core.decorators import command

if TYPE_CHECKING:
    from .plugin import MessageManagerPlugin


MAX_MESSAGES_PER_COMMAND = 10000000

async def get_contacts(client):
    """دریافت فهرست فعلی مخاطبین حساب."""
    result = await client(
        functions.contacts.GetContactsRequest(hash=0)
    )

    return list(getattr(result, "users", None) or [])


async def resolve_target(client, target_id: int):
    """پیداکردن کاربر، گروه یا کانال از گفتگوهای قابل‌دسترسی."""

    target_id = int(target_id)

    me = await client.get_me()
    my_id = getattr(me, "id", None)

    if my_id is not None and target_id == int(my_id):
        return "me"

    dialogs = await client.get_dialogs()

    for dialog in dialogs:
        entity = getattr(dialog, "entity", None)
        dialog_id = int(getattr(dialog, "id", 0) or 0)
        entity_id = getattr(entity, "id", None)

        candidates = {dialog_id, abs(dialog_id)}

        if entity_id is not None:
            entity_id = int(entity_id)
            candidates.update({entity_id, -entity_id, abs(entity_id)})

            # قالب رایج شناسهٔ کانال: -100<ID>
            if getattr(dialog, "is_channel", False):
                candidates.add(-int(f"100{entity_id}"))

                # قالب شناسهٔ علامت‌گذاری‌شدهٔ SPlusthon
                candidates.add(-(1_000_000_000_000 + entity_id))

        if target_id in candidates:
            return await client.get_input_entity(entity)

    # سازگاری با UID مثبت کاربر، حتی اگر در گفتگوها پیدا نشود.
    if target_id > 0:
        return await client.get_input_entity(target_id)

    raise ValueError(
        "گروه یا کانال با این شناسه در گفتگوهای قابل‌دسترسی پیدا نشد."
    )


@command(
    name="اسپم",
    permission="owner",
    chat_type="all",
    description="ارسال یک متن به تعداد مشخص به کاربر، گروه یا کانال.",
    native_name="send_text_messages",
)
async def send_text_messages(
    self: "MessageManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    args_text = getattr(event, "args_text", "").strip()

    # تعداد و شناسهٔ مقصد اعدادند؛ تمام باقی‌مانده متن پیام است.
    parts = args_text.split(maxsplit=2)

    if len(parts) != 3:
        await event.reply(
            "❌ قالب دستور نادرست است.\n"
            "مثال:\n"
            "`!ارسال پیام 2 -100123 سلام`\n"
            "ساختار: تعداد، شناسهٔ مقصد، متن پیام"
        )
        return

    try:
        count = int(parts[0])
        target_id = int(parts[1])
    except ValueError:
        await event.reply(
            "❌ تعداد و شناسهٔ مقصد باید عدد باشند."
        )
        return

    message_text = parts[2]

    if count <= 0 or count > MAX_MESSAGES_PER_COMMAND:
        await event.reply(
            f"❌ تعداد باید بین 1 و {MAX_MESSAGES_PER_COMMAND} باشد."
        )
        return

    if target_id == 0:
        await event.reply(
            "❌ شناسهٔ مقصد نمی‌تواند صفر باشد."
        )
        return

    if not message_text.strip():
        await event.reply(
            "❌ متن پیام نمی‌تواند خالی باشد."
        )
        return

    try:
        target = await resolve_target(
            self.client,
            target_id,
        )
    except Exception as exc:
        await event.reply(
            "❌ پیدا کردن مقصد ناموفق بود.\n"
            f"خطا: `{type(exc).__name__}: {exc}`"
        )
        return

    sent = 0
    failed = 0

    for index in range(count):
        try:
            await self.client.send_message(
                target,
                message_text,
            )
            sent += 1

        except Exception as exc:
            failed += 1
            print(
                "❌ Message Manager - "
                f"ارسال پیام {index + 1}/{count} "
                f"به {target_id} ناموفق بود: "
                f"{type(exc).__name__}: {exc}"
            )

    await event.reply(
        "📨 عملیات ارسال پیام تمام شد.\n"
        f"🎯 مقصد: `{target_id}`\n"
        f"✅ ارسال موفق: {sent}\n"
        f"❌ ارسال ناموفق: {failed}"
    )


@command(
    name="ارسال پیام به مخاطبین",
    permission="owner",
    chat_type="all",
    description="ارسال یک پیام به تمام مخاطبین حساب",
    native_name="send_message_to_contacts",
)
async def send_message_to_contacts(
    self: "MessageManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private:
        return

    # فقط مالک اجازه اجرای دستور را دارد.
    from core.permissions import is_owner

    if not is_owner(event.sender_id):
        return

    # تمام متن بعد از نام دستور، متن پیام است.
    message_text = getattr(
        event,
        "args_text",
        "",
    )

    if not message_text.strip():
        await event.reply(
            "❌ متن پیام را وارد کن.\n\n"
            "مثال:\n"
            "`!ارسال پیام به مخاطبین سلام به همه`"
        )
        return

    try:
        contacts = await get_contacts(self.client)

    except Exception as exc:
        print(
            "Message Manager - Get contacts error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ دریافت فهرست مخاطبین ناموفق بود.\n"
            f"خطا: `{type(exc).__name__}`"
        )
        return

    if not contacts:
        await event.reply(
            "ℹ️ هیچ مخاطبی برای ارسال پیام پیدا نشد."
        )
        return
    
    try:
        sent_contact_ids = await memory.get_sent_contact_ids(
            self.db
        )
    except Exception as exc:
        print(
            "Message Manager - Read memory error: "
            f"{type(exc).__name__}: {exc}"
        )
        await event.reply(
            "❌ خواندن حافظهٔ مخاطبین از دیتابیس ناموفق بود؛ "
            "برای جلوگیری از ارسال تکراری، عملیات لغو شد."
        )
        return

    # فقط مخاطب‌هایی که قبلاً پیام نگرفته‌اند باقی می‌مانند.
    contacts = [
        contact
        for contact in contacts
        if getattr(contact, "id", None) is not None
        and int(contact.id) not in sent_contact_ids
    ]

    if not contacts:
        await event.reply(
            "ℹ️ تمام مخاطبین فعلی قبلاً پیام گرفته‌اند؛ "
            "مخاطب جدیدی برای ارسال وجود ندارد."
        )
        return

    # جلوگیری از ارسال تکراری به شناسه‌های یکسان.
    unique_contacts = []
    seen_ids = set()

    for contact in contacts:
        user_id = getattr(contact, "id", None)

        if user_id is None or user_id in seen_ids:
            continue

        seen_ids.add(user_id)
        unique_contacts.append(contact)

    if not unique_contacts:
        await event.reply(
            "ℹ️ مخاطب قابل پردازشی پیدا نشد."
        )
        return

    sent = 0
    failed = 0
    processed = 0

    flood_wait_count = 0
    flood_wait_seconds_total = 0
    stopped_by_peer_flood = False

    await event.reply(
        "📨 ارسال پیام به مخاطبین شروع شد.\n"
        f"👥 تعداد مخاطبین: {len(unique_contacts)}"
    )

    for index, contact in enumerate(unique_contacts):
        user_id = getattr(contact, "id", None)
        send_succeeded = False

        # در صورت FloodWait، همان مخاطب دوباره امتحان می‌شود.
        while True:
            try:
                await self.client.send_message(
                    contact,
                    message_text,
                )

                send_succeeded = True
                break

            except FloodWaitError as exc:
                # مدت انتظار را از خود خطای سرور می‌گیریم.
                wait_seconds = max(
                    1,
                    int(getattr(exc, "seconds", 1) or 1),
                )

                flood_wait_count += 1
                flood_wait_seconds_total += wait_seconds

                print(
                    "Message Manager - FloodWait: "
                    f"user_id={user_id}, "
                    f"wait={wait_seconds}s, "
                    f"retrying_same_contact=True"
                )

                # نه مخاطب را ناموفق حساب می‌کنیم
                # و نه به مخاطب بعدی می‌رویم.
                await asyncio.sleep(wait_seconds)
                continue

            except PeerFloodError as exc:
                failed += 1
                processed += 1
                stopped_by_peer_flood = True

                print(
                    "Message Manager - PeerFlood: "
                    f"user_id={user_id}, "
                    f"{type(exc).__name__}: {exc}"
                )

                # این محدودیت را با مکث کوتاه دور نمی‌زنیم.
                break

            except Exception as exc:
                failed += 1
                processed += 1

                print(
                    "Message Manager - Send to contact failed: "
                    f"user_id={user_id}, "
                    f"{type(exc).__name__}: {exc}"
                )

                break

        # محدودیت کلی ارسال دریافت شده است.
        if stopped_by_peer_flood:
            break

        # این مخاطب به دلیل خطای دیگری ارسال ناموفق داشته است.
        if not send_succeeded:
            if index < len(unique_contacts) - 1:
                await asyncio.sleep(1)
            continue

        # فقط پس از ارسال موفق، مخاطب را در حافظه ثبت کن.
        try:
            await memory.mark_contact_sent(
                self.db,
                user_id,
            )

        except Exception as exc:
            sent += 1
            processed += 1

            print(
                "Message Manager - Save memory error: "
                f"user_id={user_id}, "
                f"{type(exc).__name__}: {exc}"
            )

            await event.reply(
                "⚠️ پیام ارسال شد، اما ثبت مخاطب در دیتابیس "
                "ناموفق بود. برای جلوگیری از ارسال تکراری، "
                "عملیات متوقف شد."
            )
            return

        sent += 1
        processed += 1

        # فاصلهٔ عادی بین دو مخاطب.
        if index < len(unique_contacts) - 1:
            await asyncio.sleep(1)

    remaining = len(unique_contacts) - processed

    report = (
        "📋 **گزارش ارسال پیام به مخاطبین**\n\n"
        f"👥 تعداد مخاطبین: {len(unique_contacts)}\n"
        f"✅ ارسال موفق: {sent}\n"
        f"❌ ارسال ناموفق: {failed}"
    )

    if flood_wait_count:
        report += (
            "\n\n⏳ **مدیریت FloodWait**\n"
            f"تعداد دفعات انتظار: {flood_wait_count}\n"
            f"مجموع زمان انتظار: {flood_wait_seconds_total} ثانیه\n"
            "پس از پایان زمان انتظار، ارسال دوباره امتحان شد."
        )

    if stopped_by_peer_flood:
        report += (
            "\n\n⚠️ **محدودیت کلی ارسال دریافت شد.**\n"
            "برای جلوگیری از تشدید محدودیت، ارسال متوقف شد.\n"
            f"⏭️ مخاطبین باقی‌مانده: {remaining}"
        )

    await event.reply(report)
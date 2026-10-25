from typing import TYPE_CHECKING

from splusthon import events, types
from core.decorators import command
from core.permissions import is_owner

from .utils import (
    get_contacts,
    get_contact_count,
    get_group_members,
    add_user_to_contacts,
)

if TYPE_CHECKING:
    from .plugin import ContactManagerPlugin



CONTACTS_LIMIT=25




@command(
    name="تعداد مخاطبین",
    permission="owner",
    chat_type="all",
    description="نمایش تعداد مخاطبین فعلی حساب",
    native_name="count_contacts",
)
async def count_contacts(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private:
        return

    if not is_owner(event.sender_id):
        return

    try:
        count = await get_contact_count(self.client)

        await event.reply(
            f"📇 **آمار مخاطبین اتریسا**\n\n"
            f"تعداد مخاطبین فعلی: **{count}**"
        )

    except Exception as exc:
        print(
            "Contact Manager - Count contacts error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ دریافت تعداد مخاطبین ناموفق بود.\n"
            f"خطا: `{type(exc).__name__}`"
        )


@command(
    name="حذف مخاطبین",
    permission="owner",
    chat_type="all",
    description="حذف تمام مخاطبین حساب یوزربات",
    native_name="delete_contacts",
)
async def delete_contacts(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private:
        return

    if not is_owner(event.sender_id):
        return

    args = getattr(event, "args_text", "").strip()

    if args != "تأیید":
        try:
            contacts = await get_contacts(self.client)

        except Exception as exc:
            print(
                "Contact Manager - Get contacts error: "
                f"{type(exc).__name__}: {exc}"
            )

            await event.reply(
                "❌ دریافت فهرست مخاطبین ناموفق بود.\n"
                f"خطا: `{type(exc).__name__}`"
            )
            return

        count = len(contacts)

        if count == 0:
            await event.reply(
                "ℹ️ هیچ مخاطبی برای حذف پیدا نشد."
            )
            return

        await event.reply(
            "⚠️ **تأیید حذف مخاطبین**\n\n"
            f"تعداد مخاطبین پیدا شده: {count}\n"
            "این عملیات مخاطبین حساب یوزربات را حذف می‌کند.\n\n"
            "برای تأیید، دستور زیر را ارسال کن:\n"
            "`!حذف مخاطبین تأیید`\n\n"
            "برای لغو، هیچ کاری نکن."
        )
        return

    try:
        contacts = await get_contacts(self.client)

        if not contacts:
            await event.reply(
                "ℹ️ هیچ مخاطبی برای حذف پیدا نشد."
            )
            return

        deleted = 0
        failed = 0

        for start in range(0, len(contacts), 50):
            batch = contacts[start:start + 50]
            input_users = []

            for user in batch:
                access_hash = getattr(user, "access_hash", None)

                if access_hash is None:
                    failed += 1
                    continue

                input_users.append(
                    types.InputUser(
                        user_id=user.id,
                        access_hash=access_hash,
                    )
                )

            if not input_users:
                continue

            try:
                from splusthon import functions

                await self.client(
                    functions.contacts.DeleteContactsRequest(
                        id=input_users
                    )
                )

                deleted += len(input_users)

            except Exception as exc:
                failed += len(input_users)

                print(
                    "Contact Manager - Delete batch error: "
                    f"{type(exc).__name__}: {exc}"
                )

        await event.reply(
            "📋 **عملیات حذف مخاطبین پایان یافت.**\n\n"
            f"✅ تعداد مخاطبین پردازش‌شده با موفقیت: {deleted}\n"
            f"❌ تعداد مخاطبین ناموفق یا غیرقابل‌پردازش: {failed}"
        )

    except Exception as exc:
        print(
            "Contact Manager - Unexpected error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ هنگام حذف مخاطبین خطایی رخ داد.\n"
            f"نوع خطا: `{type(exc).__name__}`"
        )



@command(
    name="افزودن مخاطبین گروه",
    permission="owner",
    chat_type="all",
    description="بررسی و افزودن مدیران قابل‌مشاهدهٔ گروه به مخاطبین",
    native_name="add_group_contacts",
)
async def add_group_contacts(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private or not is_owner(event.sender_id):
        return

    args = getattr(event, "args_text", "").strip()
    pending = getattr(self, "_pending_group_contacts", {})

    # مرحلهٔ دوم: تأیید افزودن
    if args == "تأیید":
        request = pending.pop(event.sender_id, None)
        self._pending_group_contacts = pending

        if not request:
            await event.reply(
                "ℹ️ درخواست معتبری برای تأیید پیدا نشد."
            )
            return

        added = 0
        failed = 0

        for user in request:
            try:
                await add_user_to_contacts(self.client, user)
                added += 1
            except Exception as exc:
                failed += 1
                print(
                    "Contact Manager - Add contact error: "
                    f"{type(exc).__name__}: {exc}"
                )

        await event.reply(
            "📇 **نتیجهٔ افزودن مخاطبین**\n\n"
            f"✅ موفق: {added}\n"
            f"❌ ناموفق: {failed}"
        )
        return

    # مرحلهٔ اول: دریافت شناسه و تعداد
    parts = args.split()

    if len(parts) != 2:
        await event.reply(
            "❌ آرگومان‌ها نامعتبرند.\n\n"
            "روش استفاده:\n"
            "`!افزودن مخاطبین گروه شناسه_گروه تعداد`\n\n"
            "مثال:\n"
            "`!افزودن مخاطبین گروه -100 25`"
        )
        return

    try:
        group_id = int(parts[0])
        requested_count = int(parts[1])
    except ValueError:
        await event.reply("❌ شناسهٔ گروه و تعداد باید عدد باشند.")
        return

    if not 1 <= requested_count <= CONTACTS_LIMIT:
        await event.reply(
            f"❌ تعداد باید بین ۱ تا {CONTACTS_LIMIT} باشد."
        )
        return

    try:
        members = await get_group_members(
            self.client,
            group_id,
            limit=requested_count,
        )

        contacts = await get_contacts(self.client)
        contact_ids = {user.id for user in contacts}

        candidates = [
            user for user in members
            if user.id not in contact_ids
            and getattr(user, "access_hash", None) is not None
        ]

        if not candidates:
            await event.reply(
                "ℹ️ مدیر قابل‌افزودن جدیدی پیدا نشد؛ "
                "ممکن است مدیران قابل‌مشاهده از قبل مخاطب باشند."
            )
            return

        self._pending_group_contacts = pending
        pending[event.sender_id] = candidates

        lines = []

        for index, user in enumerate(candidates, start=1):
            first = getattr(user, "first_name", "") or ""
            last = getattr(user, "last_name", "") or ""
            name = f"{first} {last}".strip() or "بدون نام"
            lines.append(f"{index}. {name} — شناسه `{user.id}`")

        await event.reply(
            "⚠️ **بررسی مدیران انتخاب‌شده**\n\n"
            + "\n".join(lines)
            + "\n\n"
            "این فهرست فقط شامل مدیرانی است که API برگردانده "
            "و هنوز در مخاطبین نیستند.\n"
            "اگر اجازهٔ افزودن این افراد را داری، تأیید کن:\n"
            "`!افزودن مخاطبین گروه تأیید`\n\n"
            "برای لغو، دستور تأیید را ارسال نکن."
        )

    except Exception as exc:
        print(
            "Contact Manager - Get group admins error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ دریافت مدیران گروه ناموفق بود.\n"
            "شناسه و دسترسی اتریسا به گروه را بررسی کن.\n"
            f"خطا: `{type(exc).__name__}`"
        )
from typing import TYPE_CHECKING

from splusthon import events, types
from core.decorators import command
from core.permissions import is_owner

from .utils import get_contacts, get_contact_count


if TYPE_CHECKING:
    from .plugin import ContactManagerPlugin


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
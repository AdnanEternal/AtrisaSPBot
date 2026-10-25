import asyncio
from typing import TYPE_CHECKING

from splusthon import events, types, functions
from core.decorators import command
from core.permissions import is_owner

from .utils import (
    get_contacts,
    get_contact_count,
    get_chat_member_stats,
)

if TYPE_CHECKING:
    from .plugin import ContactManagerPlugin


from .utils import (
    get_contacts,
    get_contact_count,
    get_chat_member_stats,
    get_all_members,
    resolve_chat_entity,
)

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
    name="استخراج کاربران",
    permission="owner",
    chat_type="all",
    description="نمایش آمار اعضای گروه یا کانال",
    native_name="extract_users",
)
async def extract_users(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private or not is_owner(event.sender_id):
        return

    chat_ref = getattr(event, "args_text", "").strip()

    if not chat_ref:
        await event.reply(
            "⚠️ شناسه، نام کاربری یا لینک گروه/کانال را وارد کن.\n\n"
            "مثال:\n"
            "`!استخراج کاربران 123456789`\n"
            "`!استخراج کاربران channel_username`"
        )
        return

    try:
        stats = await get_chat_member_stats(
            self.client,
            chat_ref,
        )

        title = stats["title"] or "گروه/کانال"
        total = stats["total_members"]
        retrievable = stats["retrievable_members"]

        await event.reply(
            f"📊 **آمار {title}**\n\n"
            f"👥 تعداد کل اعضا: **{total}**\n"
            f"✅ تعداد اعضای قابل استخراج: **{retrievable}**"
        )

    except Exception as exc:
        print(
            "Contact Manager - Member stats error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ دریافت آمار ناموفق بود.\n"
            f"نوع خطا: `{type(exc).__name__}`\n"
            f"جزئیات: `{str(exc)[:250]}`"
        )


@command(
    name="افزودن اعضا به مخاطبین",
    permission="owner",
    chat_type="all",
    description="افزودن اعضای گروه به مخاطبین حساب",
    native_name="add_members_to_contacts",
)
async def add_members_to_contacts(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private or not is_owner(event.sender_id):
        return

    args = getattr(event, "args_text", "").strip()
    parts = args.split()

    if len(parts) != 2:
        await event.reply(
            "⚠️ شناسه گروه و تعداد اعضا را وارد کن.\n\n"
            "مثال:\n"
            "`!افزودن اعضا به مخاطبین 123456789 100`"
        )
        return

    chat_ref, raw_limit = parts

    try:
        limit = int(raw_limit)
    except ValueError:
        await event.reply(
            "❌ تعداد اعضا باید یک عدد صحیح باشد."
        )
        return

    if limit <= 0:
        await event.reply(
            "❌ تعداد اعضا باید بیشتر از صفر باشد."
        )
        return

    try:
        entity = await resolve_chat_entity(
            self.client,
            chat_ref,
        )

        members = await get_all_members(
            self.client,
            entity,
            limit=limit,
        )

        if not members:
            await event.reply(
                "ℹ️ هیچ عضو قابل دریافت پیدا نشد."
            )
            return

        contacts = await get_contacts(self.client)

        contact_ids = {
            user.id for user in contacts
        }

        added = 0
        already = 0
        skipped = 0
        failed = 0

        seen_ids = set()
        stopped_by_rate_limit = False

        await event.reply(
            "⏳ عملیات افزودن اعضا شروع شد.\n"
            f"تعداد اعضای دریافتی: {len(members)}\n"
            "اعضا به‌ترتیب بررسی می‌شوند."
        )

        for member in members:
            user_id = getattr(member, "id", None)

            if user_id is None or user_id in seen_ids:
                continue

            seen_ids.add(user_id)

            # مخاطب تکراری اضافه نکن.
            if user_id in contact_ids:
                already += 1
                continue

            # برای افزودن مخاطب، شناسه قابل استفاده لازم است.
            access_hash = getattr(
                member,
                "access_hash",
                None,
            )

            if access_hash is None:
                skipped += 1
                continue

            first_name = str(
                getattr(member, "first_name", None) or ""
            ).strip()

            last_name = str(
                getattr(member, "last_name", None) or ""
            ).strip()

            # API نام خالی را ممکن است رد کند.
            if not first_name:
                first_name = f"عضو {user_id}"

            try:
                await self.client(
                    functions.contacts.AddContactRequest(
                        id=types.InputUser(
                            user_id=user_id,
                            access_hash=access_hash,
                        ),
                        first_name=first_name,
                        last_name=last_name,
                        phone="",
                    )
                )

                added += 1
                contact_ids.add(user_id)

            except Exception as exc:
                failed += 1

                print(
                    "Contact Manager - Add member contact error: "
                    f"user_id={user_id}, "
                    f"{type(exc).__name__}: {exc}"
                )

                # در صورت محدودیت نرخ، ادامه نده.
                error_name = type(exc).__name__.lower()
                error_text = str(exc).lower()

                if (
                    "flood" in error_name
                    or "flood" in error_text
                ):
                    stopped_by_rate_limit = True
                    break

            # کمی فاصله بین درخواست‌های افزودن مخاطب.
            await asyncio.sleep(0.25)

        message = (
            "📇 **گزارش افزودن اعضا به مخاطبین**\n\n"
            f"👥 تعداد اعضای دریافتی: {len(members)}\n"
            f"✅ افزوده‌شده: {added}\n"
            f"ℹ️ از قبل مخاطب بودند: {already}\n"
            f"⏭️ غیرقابل‌پردازش: {skipped}\n"
            f"❌ ناموفق: {failed}"
        )

        if stopped_by_rate_limit:
            message += (
                "\n\n⚠️ عملیات به‌دلیل محدودیت نرخ متوقف شد."
            )

        await event.reply(message)

    except Exception as exc:
        print(
            "Contact Manager - Add members error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ عملیات افزودن اعضا ناموفق بود.\n"
            f"نوع خطا: `{type(exc).__name__}`\n"
            f"جزئیات: `{str(exc)[:200]}`"
        )
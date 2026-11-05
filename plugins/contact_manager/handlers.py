import asyncio
from typing import TYPE_CHECKING

from splusthon import events, types, functions
from splusthon.tl.functions.channels import InviteToChannelRequest
from splusthon.tl.functions.messages import AddChatUserRequest
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


            # فقط کاربران واقعی و حذف‌نشده را بررسی کن.
            if isinstance(member, types.UserEmpty):
                skipped += 1
                continue

            if not isinstance(member, types.User):
                skipped += 1
                continue

            if getattr(member, "deleted", False):
                skipped += 1
                continue

            access_hash = getattr(member, "access_hash", None)
            is_min = bool(getattr(member, "min", False))

            if access_hash is None or is_min:
                skipped += 1
                print(
                    "Contact Manager - Skipping member: "
                    f"user_id={user_id}, "
                    f"entity_min={is_min}, "
                    f"has_access_hash={access_hash is not None}"
                )
                continue

            first_name = str(
                getattr(member, "first_name", None) or ""
            ).strip()

            last_name = str(
                getattr(member, "last_name", None) or ""
            ).strip()

            if not first_name:
                first_name = f"عضو {user_id}"

            fresh_member = None

            try:
                # موجودیت کاربر را دوباره از API دریافت کن.
                fresh_member = await self.client.get_entity(member)

                if (
                    isinstance(fresh_member, types.UserEmpty)
                    or not isinstance(fresh_member, types.User)
                    or getattr(fresh_member, "deleted", False)
                ):
                    skipped += 1
                    continue

                await self.client(
                    functions.contacts.AddContactRequest(
                        id=fresh_member,
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
                    f"refreshed_entity={fresh_member is not None}, "
                    f"{type(exc).__name__}: {exc}"
                )

                error_name = type(exc).__name__.lower()
                error_text = str(exc).lower()

                if "flood" in error_name or "flood" in error_text:
                    stopped_by_rate_limit = True
                    break
                # کمی فاصله بین درخواست‌های افزودن مخاطب.


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

        
@command(
    name="افزودن مخاطبین به گروه",
    permission="owner",
    chat_type="all",
    description="افزودن مخاطبین حساب به گروه یا کانال",
    native_name="add_contacts_to_chat",
)
async def add_contacts_to_chat(
    self: "ContactManagerPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.is_private or not is_owner(event.sender_id):
        return

    args = getattr(event, "args_text", "").strip()
    parts = args.split()

    if len(parts) != 2:
        await event.reply(
            "⚠️ شناسه یا نام کاربری مقصد و تعداد مخاطبین را وارد کن.\n\n"
            "مثال:\n"
            "`!افزودن مخاطبین به گروه 123456789 2`"
        )
        return

    chat_ref, raw_limit = parts

    try:
        limit = int(raw_limit)
    except ValueError:
        await event.reply("❌ تعداد باید عدد صحیح باشد.")
        return

    if not 1 <= limit <= 1000:
        await event.reply(
            "❌ تعداد باید بین ۱ تا ۱۰ باشد."
        )
        return

    try:
        # پیدا کردن مقصد
        entity = await resolve_chat_entity(
            self.client,
            chat_ref,
        )

        # دریافت مخاطبین
        contacts = await get_contacts(self.client)

        # انتخاب اولین مخاطبین قابل پردازش
        candidates = []
        seen_ids = set()

        for user in contacts:
            user_id = getattr(user, "id", None)

            if user_id is None or user_id in seen_ids:
                continue

            seen_ids.add(user_id)

            if not isinstance(user, types.User):
                continue

            if getattr(user, "deleted", False):
                continue

            if getattr(user, "min", False):
                continue

            if getattr(user, "access_hash", None) is None:
                continue

            candidates.append(user)

            if len(candidates) >= limit:
                break

        if not candidates:
            await event.reply(
                "ℹ️ هیچ مخاطب قابل پردازشی پیدا نشد."
            )
            return

        title = getattr(entity, "title", None) or "گروه/کانال"

        await event.reply(
            "⏳ **عملیات افزودن مخاطبین شروع شد.**\n\n"
            f"🎯 مقصد: {title}\n"
            f"👥 تعداد مخاطبین انتخاب‌شده: {len(candidates)}"
        )

        added = 0
        already = 0
        skipped = 0
        failed = 0

        stopped_by_flood = False
        flood_seconds = None

        for index, contact in enumerate(candidates):
            try:
                # تازه‌سازی اطلاعات مخاطب
                fresh_contact = await self.client.get_entity(
                    contact
                )

                if (
                    not isinstance(fresh_contact, types.User)
                    or getattr(fresh_contact, "deleted", False)
                    or getattr(fresh_contact, "min", False)
                    or getattr(fresh_contact, "access_hash", None) is None
                ):
                    skipped += 1

                else:
                    # کانال و سوپرگروه
                    if isinstance(entity, types.Channel):
                        await self.client(
                            InviteToChannelRequest(
                                channel=entity,
                                users=[fresh_contact],
                            )
                        )

                    # گروه معمولی
                    elif isinstance(entity, types.Chat):
                        await self.client(
                            AddChatUserRequest(
                                chat_id=entity.id,
                                user_id=fresh_contact,
                                fwd_limit=0,
                            )
                        )

                    else:
                        skipped += 1
                        continue

                    added += 1

            except Exception as exc:
                error_text = (
                    f"{type(exc).__name__} {exc}"
                ).upper()

                if "FLOOD" in error_text:
                    stopped_by_flood = True
                    flood_seconds = getattr(
                        exc, "seconds", None
                    )
                    print(
                        "Contact Manager - Invite flood limit: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    break

                elif (
                    "USER_ALREADY_PARTICIPANT" in error_text
                    or "USER_ALREADY_IN_CHAT" in error_text
                ):
                    already += 1

                else:
                    failed += 1

                    print(
                        "Contact Manager - Invite contact error: "
                        f"user_id={getattr(contact, 'id', None)}, "
                        f"{type(exc).__name__}: {exc}"
                    )

            # فاصله بین درخواست‌ها
            if index < len(candidates) - 1:
                await asyncio.sleep(1)

        # گزارش نهایی
        message = (
            "📋 **گزارش افزودن مخاطبین**\n\n"
            f"🎯 مقصد: **{title}**\n"
            f"👥 مخاطبین انتخاب‌شده: {len(candidates)}\n\n"
            f"✅ با موفقیت افزوده‌شده: {added}\n"
            f"ℹ️ از قبل عضو بودند: {already}\n"
            f"⏭️ غیرقابل‌پردازش: {skipped}\n"
            f"❌ ناموفق: {failed}"
        )

        if stopped_by_flood:
            message += (
                "\n\n⚠️ عملیات به دلیل محدودیت درخواست‌های سروش متوقف شد."
            )

            if flood_seconds is not None:
                message += (
                    f"\nزمان اعلام‌شده توسط سرور: {flood_seconds} ثانیه"
                )

        await event.reply(message)

    except Exception as exc:
        print(
            "Contact Manager - Add contacts to chat error: "
            f"{type(exc).__name__}: {exc}"
        )

        await event.reply(
            "❌ عملیات افزودن مخاطبین ناموفق بود.\n"
            f"نوع خطا: `{type(exc).__name__}`\n"
            f"جزئیات: `{str(exc)[:200]}`"
        )

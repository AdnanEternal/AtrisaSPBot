
from typing import TYPE_CHECKING

from splusthon import events

from core.decorators import command

if TYPE_CHECKING:
    from .plugin import MessageManagerPlugin


MAX_MESSAGES_PER_COMMAND = 10000000


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

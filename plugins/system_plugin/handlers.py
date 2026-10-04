from typing import TYPE_CHECKING

from splusthon import events

from core.decorators import command
from core.permissions import is_owner

from .backup.backup import DatabaseBackupManager
from .github_manager.manager import GitHubManager
from .plugin_updater import PluginUpdateManager


if TYPE_CHECKING:
    from .plugin import SystemPlugin


HELP_PAGE_SIZE = 6


@command(
    name="راهنما",
    permission="everyone",
    chat_type="private",
    description="❓ لیست کامندهای قابل استفاده را نشان می‌دهد.",
)
async def show_help(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    sender_id = event.sender_id

    is_owner_user = is_owner(sender_id)

    if is_owner_user:
        allowed_permissions = {
            "everyone",
            "admin",
            "owner",
        }
    else:
        allowed_permissions = {
            "everyone",
        }

    commands = [
        cmd
        for cmd in self.command_manager.get_all_commands()
        if (
            cmd.permission in allowed_permissions
            and cmd.chat_type == "private"
        )
    ]

    commands.sort(
        key=lambda cmd: cmd.name
    )

    if not commands:
        await event.reply(
            "📖 هیچ کامندی برای نمایش وجود ندارد."
        )
        return

    try:
        page = (
            int(event.args[0])
            if event.args
            else 1
        )

    except (
        ValueError,
        TypeError,
    ):
        page = 1

    if page < 1:
        page = 1

    total_pages = (
        len(commands)
        + HELP_PAGE_SIZE
        - 1
    ) // HELP_PAGE_SIZE

    if page > total_pages:
        page = total_pages

    start = (
        page - 1
    ) * HELP_PAGE_SIZE

    end = (
        start
        + HELP_PAGE_SIZE
    )

    page_commands = commands[
        start:end
    ]

    lines = [
        (
            f"`!{cmd.name}`\n"
            f"{cmd.description or 'بدون توضیح'}"
        )
        for cmd in page_commands
    ]

    text = (
        f"📖 راهنما — صفحه "
        f"{page}/{total_pages}\n\n"
        + "\n\n".join(lines)
    )

    if total_pages > 1:
        if page < total_pages:
            text += (
                "\n\n"
                f"📄 برای صفحه بعد: "
                f"`!راهنما {page + 1}`"
            )
        else:
            text += (
                "\n\n"
                f"📄 برای صفحه قبل: "
                f"`!راهنما {page - 1}`"
            )

    await event.reply(text)


@command(
    name="گیتهاب چک",
    permission="owner",
    chat_type="private",
    description=(
        "🔗 اتصال ربات به مخزن GitHub "
        "را بررسی می‌کند."
    ),
)
async def github_check(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    try:
        github = GitHubManager()

        await github.check_connection()

    except Exception as exc:
        await event.reply(
            "❌ اتصال به GitHub ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    await event.reply(
        "✅ اتصال به GitHub "
        "با موفقیت برقرار شد."
    )


@command(
    name="دیتابیس بکاپ",
    permission="owner",
    chat_type="private",
    description=(
        "💾 یک نسخه از دیتابیس را "
        "در GitHub ذخیره می‌کند."
    ),
)
async def database_backup(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    try:
        github = GitHubManager()

        backup = DatabaseBackupManager(
            db=self.db,
            github=github,
        )

        await backup.create_backup()

    except Exception as exc:
        await event.reply(
            "❌ بکاپ دیتابیس ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    await event.reply(
        "✅ بکاپ دیتابیس با موفقیت "
        "در GitHub ذخیره شد."
    )


@command(
    name="دیتابیس بازیابی",
    permission="owner",
    chat_type="private",
    description=(
        "♻️ دیتابیس را از آخرین بکاپ "
        "GitHub بازیابی می‌کند."
    ),
)
async def database_restore(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    try:
        github = GitHubManager()

        backup = DatabaseBackupManager(
            db=self.db,
            github=github,
        )

        await backup.restore_backup()

        for plugin in (
            self.plugin_manager.get_all_plugins()
        ):
            try:
                await plugin.on_load()

            except Exception as exc:
                print(
                    "❌ خطا در بازسازی دیتابیس پلاگین "
                    f"'{plugin.name}': {exc}"
                )

    except Exception as exc:
        await event.reply(
            "❌ بازیابی دیتابیس ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    await event.reply(
        "✅ دیتابیس با موفقیت از "
        "آخرین بکاپ GitHub بازیابی شد."
    )


@command(
    name="لیست پلاگین ها",
    permission="owner",
    chat_type="private",
    description=(
        "📦 لیست پلاگین‌های نصب‌شده "
        "و نسخه‌ی آن‌ها را نشان می‌دهد."
    ),
)
async def list_plugins(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    plugins = (
        self.plugin_manager.get_all_plugins()
    )

    if not plugins:
        await event.reply(
            "📦 هیچ پلاگینی نصب نشده."
        )
        return

    lines = [
        (
            f"🔹 **{plugin.name}** — "
            f"version: {plugin.version}"
        )
        for plugin in sorted(
            plugins,
            key=lambda plugin: (
                plugin.name.lower()
            ),
        )
    ]

    await event.reply(
        "📦 پلاگین‌های نصب‌شده:\n\n"
        + "\n".join(lines)
    )


@command(
    name="پلاگین آپدیت چک",
    permission="owner",
    chat_type="private",
    description=(
        "🔄 وجود پلاگین جدید یا نسخه‌ی "
        "جدید پلاگین‌ها را بررسی می‌کند."
    ),
)
async def plugin_update_check(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    try:
        github = GitHubManager()

        updater = PluginUpdateManager(
            plugin_manager=self.plugin_manager,
            github=github,
        )

        result = await updater.check()

    except Exception as exc:
        await event.reply(
            "❌ بررسی پلاگین‌ها ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    lines = []

    if result.new_plugins:
        lines.append(
            "📦 پلاگین‌های جدید:"
        )

        for plugin in result.new_plugins:
            lines.append(
                f"🔹 {plugin.name} — "
                f"v{plugin.version}"
            )

    if result.updates:
        if lines:
            lines.append("")

        lines.append(
            "🔄 بروزرسانی‌های موجود:"
        )

        for (
            plugin,
            local_version,
        ) in result.updates:
            lines.append(
                f"🔹 {plugin.name} — "
                f"v{local_version} "
                f"→ v{plugin.version}"
            )

    if not lines:
        await event.reply(
            "✅ هیچ پلاگین جدید یا "
            "بروزرسانی‌ای پیدا نشد."
        )
        return

    await event.reply(
        "\n".join(lines)
    )


@command(
    name="پلاگین دریافت",
    permission="owner",
    chat_type="private",
    description=(
        "📥 یک پلاگین را از GitHub "
        "دریافت و در runtime فعال می‌کند."
    ),
)
async def plugin_install(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.args:
        await event.reply(
            "❌ شناسه‌ی پلاگین را وارد کن.\n"
            "مثال:\n"
            "`!پلاگین دریافت message_manager`"
        )
        return

    plugin_id = event.args[0]

    try:
        github = GitHubManager()

        updater = PluginUpdateManager(
            plugin_manager=self.plugin_manager,
            github=github,
        )

        async with self.runtime_update_lock:
            plugin = await updater.install(
                plugin_id
            )

    except Exception as exc:
        await event.reply(
            "❌ دریافت پلاگین ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    await event.reply(
        f"✅ پلاگین «{plugin.name}» "
        f"v{plugin.version} "
        "در runtime نصب و فعال شد."
    )


@command(
    name="پلاگین آپدیت",
    permission="owner",
    chat_type="private",
    description=(
        "🔄 یک پلاگین را در runtime "
        "به‌روزرسانی می‌کند."
    ),
)
async def plugin_update(
    self: "SystemPlugin",
    event: events.NewMessage.Event,
) -> None:
    if not event.args:
        await event.reply(
            "❌ شناسه‌ی پلاگین را وارد کن.\n"
            "مثال:\n"
            "`!پلاگین آپدیت violation_manager`"
        )
        return

    plugin_id = event.args[0]

    try:
        github = GitHubManager()

        updater = PluginUpdateManager(
            plugin_manager=self.plugin_manager,
            github=github,
        )

        async with self.runtime_update_lock:
            plugin = await updater.update(
                plugin_id
            )

    except Exception as exc:
        await event.reply(
            "❌ بروزرسانی پلاگین ناموفق بود.\n"
            f"`{exc}`"
        )
        return

    await event.reply(
        f"✅ پلاگین «{plugin.name}» "
        f"به v{plugin.version} "
        "در runtime بروزرسانی شد."
    )
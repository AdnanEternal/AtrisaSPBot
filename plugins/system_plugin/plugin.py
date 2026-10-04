import asyncio

from core.base_plugin import BasePlugin

from . import handlers


class SystemPlugin(BasePlugin):
    """
    پلاگین سیستمی آتریسا.

    تمام commandهای این پلاگین فقط از PV قابل استفاده هستند.
    """

    def __init__(
        self,
        client,
        command_manager,
        db,
        event_bus,
    ):
        super().__init__(
            client,
            command_manager,
            db,
            event_bus,
        )

        self.runtime_update_lock = asyncio.Lock()

    name = "System"
    version = "2.9.11"

    show_help = handlers.show_help
    github_check = handlers.github_check
    database_backup = handlers.database_backup
    database_restore = handlers.database_restore
    list_plugins = handlers.list_plugins
    plugin_update_check = handlers.plugin_update_check
    plugin_install = handlers.plugin_install
    plugin_update = handlers.plugin_update
from core.base_plugin import BasePlugin

from . import handlers


class GroupJoinerPlugin(BasePlugin):
    name = "Group Joiner"
    version = "0.1.0"

    on_message = handlers.on_message

from core.base_plugin import BasePlugin

from . import handlers


class MessageManagerPlugin(BasePlugin):
    name = "Message Manager"
    version = "1.1.0"

    send_text_messages = handlers.send_text_messages
    send_message_to_contacts = handlers.send_message_to_contacts


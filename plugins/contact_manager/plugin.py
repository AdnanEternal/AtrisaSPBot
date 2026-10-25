from core.base_plugin import BasePlugin
from . import handlers


class ContactManagerPlugin(BasePlugin):
    name = "Contact Manager"
    version = "1.1.0"

    delete_contacts = handlers.delete_contacts
    count_contacts = handlers.count_contacts
from core.base_plugin import BasePlugin
from . import handlers


class ContactManagerPlugin(BasePlugin):
    name = "Contact Manager"
    version = "1.2.0"

    delete_contacts = handlers.delete_contacts
    count_contacts = handlers.count_contacts
    extract_users = handlers.extract_users
    add_members_to_contacts = handlers.add_members_to_contacts
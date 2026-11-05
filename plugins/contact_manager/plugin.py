from core.base_plugin import BasePlugin
from . import handlers


class ContactManagerPlugin(BasePlugin):
    name = "Contact Manager"
    version = "1.3.1"

    delete_contacts = handlers.delete_contacts
    count_contacts = handlers.count_contacts
    extract_users = handlers.extract_users
    add_members_to_contacts = handlers.add_members_to_contacts
    add_contacts_to_chat = handlers.add_contacts_to_chat
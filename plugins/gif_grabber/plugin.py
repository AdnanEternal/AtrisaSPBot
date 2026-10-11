from typing import TYPE_CHECKING

from splusthon import events

if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


class GifGrabberPlugin:
    def __init__(self, client):
        self.client = client
        self.last_gif = None

    async def on_message(self, event: events.NewMessage.Event):
        message = event.message

        if not getattr(message, "gif", None):
            return

        self.last_gif = {
            "chat_id": event.chat_id,
            "message_id": message.id,
        }
from core.base_plugin import BasePlugin

from . import handlers


class GifGrabberPlugin(BasePlugin):
    name = "GIF Grabber"
    version = "0.1.0"

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
        self.last_gif = None
        self.last_gif_message = None

    on_message = handlers.on_message
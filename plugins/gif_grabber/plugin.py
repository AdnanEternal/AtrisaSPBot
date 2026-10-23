from core.base_plugin import BasePlugin

from . import handlers, sender


class GifGrabberPlugin(BasePlugin):
    name = "GIF Grabber"
    version = "1.4.1"

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
        self._gif_send_tasks = {}
        self._gif_send_jobs = {}
        self._gif_send_next_id = 1

    on_message = handlers.on_message
    fetch_gifs = handlers.fetch_gifs
    clear_saved_gifs = handlers.clear_saved_gifs
    send_gifs = handlers.send_gifs
    set_gif_repeats = handlers.set_gif_repeats
    stop_send_gifs = handlers.stop_send_gifs
    gif_stats = handlers.gif_stats



    async def on_disable(self) -> None:
        await sender.shutdown_send_tasks(self)
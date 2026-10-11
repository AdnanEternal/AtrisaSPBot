from typing import TYPE_CHECKING

from splusthon import events
from splusthon.tl.functions.messages import SaveGifRequest

from core.decorators import on_event


if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin


@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    if event.is_group is not True:
        return

    gif = event.message.gif

    if gif is None:
        return

    try:
        await self.client(
            SaveGifRequest(
                id=gif,
                unsave=False,
            )
        )

    except Exception as exc:
        print(
            "❌ GIF Grabber - "
            f"ذخیره گیف ناموفق بود: {exc}"
        )
        return

    print("✅ GIF Grabber - گیف به Saved GIFs اضافه شد.")
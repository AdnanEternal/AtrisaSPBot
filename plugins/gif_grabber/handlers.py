from typing import TYPE_CHECKING

from splusthon import events
from splusthon.tl.functions.messages import (
    SaveGifRequest,
    GetSavedGifsRequest
)

from core.decorators import command, on_event


if TYPE_CHECKING:
    from .plugin import GifGrabberPlugin






async def get_saved_gifs(client) -> list:
    result = await client(
        GetSavedGifsRequest(hash=0)
    )

    return list(
        getattr(result, "gifs", None) or []
    )





@on_event(events.NewMessage(incoming=True))
async def on_message(
    self: "GifGrabberPlugin",
    event: events.NewMessage.Event,
) -> None:
    

    if (
        event.is_group is not True
        and event.is_channel is not True
    ):
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

    # print("✅ GIF Grabber - گیف به Saved GIFs اضافه شد.")
    print(event)
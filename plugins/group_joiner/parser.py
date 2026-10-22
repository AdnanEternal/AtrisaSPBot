
import re


# لینک دعوت خصوصی
_INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/joingroup/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# لینک عمومی گروه یا کانال
_PUBLIC_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/"
    r"(?!joingroup(?:/|[?#\s]|$))"
    r"([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# شناسهٔ عددی چت
_CHAT_ID_RE = re.compile(r"-?\d+")


def extract_join_target(
    text: str,
) -> tuple[str, str] | None:
    """تشخیص لینک دعوت، لینک عمومی یا شناسهٔ عددی چت."""

    text = (text or "").strip()

    if not text:
        return None

    # شناسه باید به‌تنهایی در پیام ارسال شده باشد.
    if _CHAT_ID_RE.fullmatch(text):
        return "chat_id", text

    invite_match = _INVITE_LINK_RE.search(text)

    if invite_match is not None:
        return "invite", invite_match.group(1)

    public_match = _PUBLIC_LINK_RE.search(text)

    if public_match is not None:
        return "public", public_match.group(1)

    return None

import re


# لینک دعوت خصوصی گروه یا کانال
_INVITE_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/joingroup/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


# لینک عمومی گروه یا کانال
# فقط لینک خود مقصد پذیرفته می‌شود، نه لینک یک پیام داخل آن.
_PUBLIC_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"splus\.ir/"
    r"(?!joingroup(?:/|[?#\s]|$))"
    r"([A-Za-z0-9_-]+)"
    r"/?(?=$|[?#\s)\]\.,;!؟،؛>])",
    re.IGNORECASE,
)


def extract_join_target(
    text: str,
) -> tuple[str, str] | None:
    """استخراج لینک دعوت یا لینک مستقیم گروه و کانال."""

    text = (text or "").strip()

    if not text:
        return None

    invite_match = _INVITE_LINK_RE.search(text)

    if invite_match is not None:
        return "invite", invite_match.group(1)

    public_match = _PUBLIC_LINK_RE.search(text)

    if public_match is not None:
        return "public", public_match.group(1)

    return None
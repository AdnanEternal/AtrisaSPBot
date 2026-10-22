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


def extract_join_target(
    text: str,
) -> tuple[str, str] | None:
    """استخراج مقصد عضویت از متن پیام."""

    text = text or ""

    invite_match = _INVITE_LINK_RE.search(text)

    if invite_match is not None:
        return "invite", invite_match.group(1)

    public_match = _PUBLIC_LINK_RE.search(text)

    if public_match is not None:
        return "public", public_match.group(1)

    return None
import time


TABLE_NAME = "all_saved_gifs"
TAGS_TABLE_NAME = "gif_tags"

GIF_CHAT_SETTINGS_TABLE_NAME = "gif_chat_settings"
GIF_SENT_HISTORY_TABLE_NAME = "gif_sent_history"


async def initialize(db) -> None:
    """ساخت جدول‌های بانک گیف و تنظیمات و سابقهٔ ارسال."""

    await db.create_table(
        TABLE_NAME,
        columns={
            "doc_id": "INTEGER NOT NULL",
            "access_hash": "INTEGER NOT NULL",
        },
        unique=[["doc_id", "access_hash"]],
    )

    await db.create_table(
        TAGS_TABLE_NAME,
        columns={
            "doc_id": "INTEGER NOT NULL",
            "access_hash": "INTEGER NOT NULL",
            "tag": "TEXT NOT NULL",
        },
        unique=[["doc_id", "access_hash", "tag"]],
        indexes=["tag"],
    )

    await db.create_table(
        GIF_CHAT_SETTINGS_TABLE_NAME,
        columns={
            "chat_id": "INTEGER NOT NULL",
            "allow_repeats": "INTEGER NOT NULL DEFAULT 1",
        },
        unique=[["chat_id"]],
    )

    await db.create_table(
        GIF_SENT_HISTORY_TABLE_NAME,
        columns={
            "chat_id": "INTEGER NOT NULL",
            "doc_id": "INTEGER NOT NULL",
            "access_hash": "INTEGER NOT NULL",
            "sent_at": "REAL NOT NULL",
        },
        unique=[["chat_id", "doc_id", "access_hash"]],
        indexes=["chat_id"],
    )


def _normalize_tags(tags) -> list[str]:
    """حذف تگ‌های خالی و تکراری بدون تغییر ترتیب ورودی."""

    result = []
    seen = set()

    for tag in tags or []:
        if not isinstance(tag, str):
            continue

        tag = tag.strip()

        if not tag or tag in seen:
            continue

        seen.add(tag)
        result.append(tag)

    return result


async def remember_gif(
    db,
    doc_id: int,
    access_hash: int,
    tags=None,
) -> bool:
    """ثبت گیف و افزودن تگ‌های جدید بدون حذف تگ‌های قبلی."""

    doc_id = int(doc_id)
    access_hash = int(access_hash)

    result = await db.insert(
        TABLE_NAME,
        {
            "doc_id": doc_id,
            "access_hash": access_hash,
        },
        or_ignore=True,
    )

    for tag in _normalize_tags(tags):
        await db.insert(
            TAGS_TABLE_NAME,
            {
                "doc_id": doc_id,
                "access_hash": access_hash,
                "tag": tag,
            },
            or_ignore=True,
        )

    return result.rowcount > 0


async def get_gif_statistics(
    db,
    tag_limit: int = 10,
) -> tuple[int, list]:
    """تعداد گیف‌ها و پرتکرارترین تگ‌ها."""

    await initialize(db)

    tag_limit = max(0, int(tag_limit))

    total_row = await db.fetchone(
        f"""
        SELECT COUNT(*) AS total
        FROM {TABLE_NAME}
        """
    )

    total_gifs = int(total_row["total"] or 0)

    top_tags = await db.fetchall(
        f"""
        SELECT
            t.tag,
            COUNT(*) AS gif_count
        FROM {TAGS_TABLE_NAME} AS t
        INNER JOIN {TABLE_NAME} AS g
          ON g.doc_id = t.doc_id
         AND g.access_hash = t.access_hash
        GROUP BY t.tag
        ORDER BY gif_count DESC, t.tag COLLATE NOCASE ASC
        LIMIT ?
        """,
        (tag_limit,),
    )

    return total_gifs, top_tags


async def get_gifs(
    db,
    count: int,
    tags=None,
) -> list:
    """
    انتخاب مستقیم گیف‌ها از بانک.

    در صورت تعیین تگ، گیف باید تمام تگ‌های درخواستی را داشته باشد.
    ترتیب انتخاب اهمیتی ندارد؛ از انتخاب تصادفی استفاده نمی‌شود.
    """

    await initialize(db)

    count = max(0, int(count))

    if count == 0:
        return []

    normalized_tags = _normalize_tags(tags)

    if not normalized_tags:
        return await db.fetchall(
            f"""
            SELECT doc_id, access_hash
            FROM {TABLE_NAME}
            LIMIT ?
            """,
            (count,),
        )

    placeholders = ", ".join(
        "?" for _ in normalized_tags
    )

    return await db.fetchall(
        f"""
        SELECT
            g.doc_id,
            g.access_hash
        FROM {TABLE_NAME} AS g
        WHERE (
            SELECT COUNT(DISTINCT t.tag)
            FROM {TAGS_TABLE_NAME} AS t
            WHERE t.doc_id = g.doc_id
              AND t.access_hash = g.access_hash
              AND t.tag IN ({placeholders})
        ) = ?
        LIMIT ?
        """,
        tuple(normalized_tags) + (
            len(normalized_tags),
            count,
        ),
    )


async def get_gifs_for_chat(
    db,
    count: int,
    chat_id: int,
    tags=None,
    reserved_gifs=None,
) -> list:
    """
    انتخاب گیف‌هایی که در مقصد قبلاً ارسال نشده‌اند.

    گیف‌های رزروشده برای ارسال‌های فعال نیز انتخاب نمی‌شوند.
    در صورت تعیین چند تگ، وجود تمام تگ‌ها الزامی است.
    """

    await initialize(db)

    count = max(0, int(count))
    chat_id = int(chat_id)

    if count == 0:
        return []

    normalized_tags = _normalize_tags(tags)

    reserved = {
        (int(doc_id), int(access_hash))
        for doc_id, access_hash in (reserved_gifs or ())
    }

    # با توجه به تعداد رزروها کمی بیشتر از تعداد درخواستی
    # از دیتابیس می‌خوانیم تا بعد از کنارگذاشتن رزروها
    # همچنان بتوانیم تعداد کافی گیف انتخاب کنیم.
    fetch_count = count + len(reserved)

    if normalized_tags:
        placeholders = ", ".join(
            "?" for _ in normalized_tags
        )

        query = f"""
            SELECT
                g.doc_id,
                g.access_hash
            FROM {TABLE_NAME} AS g
            WHERE (
                SELECT COUNT(DISTINCT t.tag)
                FROM {TAGS_TABLE_NAME} AS t
                WHERE t.doc_id = g.doc_id
                  AND t.access_hash = g.access_hash
                  AND t.tag IN ({placeholders})
            ) = ?
            AND NOT EXISTS (
                SELECT 1
                FROM {GIF_SENT_HISTORY_TABLE_NAME} AS h
                WHERE h.chat_id = ?
                  AND h.doc_id = g.doc_id
                  AND h.access_hash = g.access_hash
            )
            LIMIT ?
        """

        params = tuple(normalized_tags) + (
            len(normalized_tags),
            chat_id,
            fetch_count,
        )

    else:
        query = f"""
            SELECT
                g.doc_id,
                g.access_hash
            FROM {TABLE_NAME} AS g
            WHERE NOT EXISTS (
                SELECT 1
                FROM {GIF_SENT_HISTORY_TABLE_NAME} AS h
                WHERE h.chat_id = ?
                  AND h.doc_id = g.doc_id
                  AND h.access_hash = g.access_hash
            )
            LIMIT ?
        """

        params = (
            chat_id,
            fetch_count,
        )

    rows = await db.fetchall(
        query,
        params,
    )

    selected = []

    for row in rows:
        key = (
            int(row["doc_id"]),
            int(row["access_hash"]),
        )

        if key in reserved:
            continue

        selected.append(row)

        if len(selected) >= count:
            break

    return selected


async def get_chat_repeats(
    db,
    chat_id: int,
) -> bool:
    """بررسی مجازبودن ارسال گیف تکراری برای یک مقصد."""

    await initialize(db)

    row = await db.fetchone(
        f"""
        SELECT allow_repeats
        FROM {GIF_CHAT_SETTINGS_TABLE_NAME}
        WHERE chat_id = ?
        """,
        (int(chat_id),),
    )

    # حفظ رفتار قبلی برای مقصدهای تنظیم‌نشده
    if row is None:
        return True

    return bool(int(row["allow_repeats"]))


async def set_chat_repeats(
    db,
    chat_id: int,
    allow_repeats: bool,
) -> None:
    """ثبت یا تغییر تنظیم تکرار گیف برای یک مقصد."""

    await initialize(db)

    await db.execute(
        f"""
        INSERT INTO {GIF_CHAT_SETTINGS_TABLE_NAME}
            (chat_id, allow_repeats)
        VALUES (?, ?)
        ON CONFLICT(chat_id)
        DO UPDATE SET
            allow_repeats = excluded.allow_repeats
        """,
        (
            int(chat_id),
            1 if allow_repeats else 0,
        ),
    )


async def remember_sent_gif(
    db,
    chat_id: int,
    doc_id: int,
    access_hash: int,
) -> None:
    """ثبت گیف پس از ارسال موفق."""

    await db.insert(
        GIF_SENT_HISTORY_TABLE_NAME,
        {
            "chat_id": int(chat_id),
            "doc_id": int(doc_id),
            "access_hash": int(access_hash),
            "sent_at": time.time(),
        },
        or_ignore=True,
    )
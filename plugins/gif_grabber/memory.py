
import random

TABLE_NAME = "all_saved_gifs"
TAGS_TABLE_NAME = "gif_tags"


async def initialize(db) -> None:
    """ساخت بانک مرکزی گیف‌ها و جدول تگ‌ها در صورت نیاز."""

    await db.create_table(
        TABLE_NAME,
        columns={
            "doc_id": "INTEGER NOT NULL",
            "access_hash": "INTEGER NOT NULL",
        },
        unique=[
            ["doc_id", "access_hash"],
        ],
    )

    await db.create_table(
        TAGS_TABLE_NAME,
        columns={
            "doc_id": "INTEGER NOT NULL",
            "access_hash": "INTEGER NOT NULL",
            "tag": "TEXT NOT NULL",
        },
        unique=[
            ["doc_id", "access_hash", "tag"],
        ],
        indexes=["tag"],
    )


async def remember_gif(
    db,
    doc_id: int,
    access_hash: int,
    tags=None,
) -> bool:
    """
    گیف را در بانک مرکزی ثبت می‌کند و تگ‌های جدیدش را اضافه می‌کند.

    True: رکورد گیف جدید بود.
    False: گیف از قبل وجود داشت.

    تگ‌های قبلی هرگز حذف یا جایگزین نمی‌شوند.
    """

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

    # حتی اگر خود گیف تکراری باشد، تگ‌های جدیدش باید اضافه شوند.
    if tags:
        normalized_tags = []
        seen_tags = set()

        for tag in tags:
            if not isinstance(tag, str):
                continue

            tag = tag.strip()

            if not tag or tag in seen_tags:
                continue

            seen_tags.add(tag)
            normalized_tags.append(tag)

        for tag in normalized_tags:
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
    """تعداد کل گیف‌ها و پرتکرارترین تگ‌ها را برمی‌گرداند."""

    await initialize(db)

    tag_limit = max(0, int(tag_limit))

    # تعداد کل گیف‌های یکتای بانک مرکزی
    total_row = await db.fetchone(
        f"SELECT COUNT(*) AS total "
        f"FROM {TABLE_NAME}"
    )

    total_gifs = int(total_row["total"] or 0)

    # پرتکرارترین تگ‌ها؛ هر ردیف نمایندهٔ یک گیف-تگ است.
    # اتصال به جدول اصلی نیز مانع شمارش تگ‌های بدون گیف موجود می‌شود.
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




async def get_random_gifs(db, count: int) -> list:
    """انتخاب چند گیف تصادفی بدون خواندن کل بانک در حافظه."""

    await initialize(db)

    count = max(0, int(count))

    if count == 0:
        return []

    stats = await db.fetchone(
        f"SELECT COUNT(*) AS total, MAX(rowid) AS max_rowid "
        f"FROM {TABLE_NAME}"
    )

    total = stats["total"]
    max_rowid = stats["max_rowid"]

    if not total or not max_rowid:
        return []

    target_count = min(count, total)
    selected = {}

    attempts = 0
    max_attempts = target_count * 20 + 100

    while (
        len(selected) < target_count
        and attempts < max_attempts
    ):
        attempts += 1
        row_id = random.randint(1, max_rowid)

        row = await db.fetchone(
            f"SELECT doc_id, access_hash "
            f"FROM {TABLE_NAME} "
            "WHERE rowid >= ? ORDER BY rowid LIMIT 1",
            (row_id,),
        )

        if row is None:
            row = await db.fetchone(
                f"SELECT doc_id, access_hash "
                f"FROM {TABLE_NAME} "
                "ORDER BY rowid LIMIT 1"
            )

        if row is not None:
            key = (row["doc_id"], row["access_hash"])
            selected[key] = row

    if len(selected) < target_count:
        rows = await db.fetchall(
            f"SELECT doc_id, access_hash "
            f"FROM {TABLE_NAME} "
            "ORDER BY RANDOM() LIMIT ?",
            (target_count,),
        )

        for row in rows:
            key = (row["doc_id"], row["access_hash"])
            selected[key] = row

            if len(selected) >= target_count:
                break

    return list(selected.values())[:target_count]

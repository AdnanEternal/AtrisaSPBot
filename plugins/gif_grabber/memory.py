import random

TABLE_NAME = "all_saved_gifs"


async def initialize(db) -> None:
    """ایجاد جدول بانک مرکزی گیف‌ها، در صورت نیاز."""
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


async def remember_gif(
    db,
    doc_id: int,
    access_hash: int,
) -> bool:
    """
    ثبت شناسهٔ گیف در بانک مرکزی.

    True: رکورد جدید ثبت شد.
    False: این ترکیب قبلاً ثبت شده بود.
    """
    result = await db.insert(
        TABLE_NAME,
        {
            "doc_id": int(doc_id),
            "access_hash": int(access_hash),
        },
        or_ignore=True,
    )

    return result.rowcount > 0






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

    # انتخاب تصادفی با استفاده از rowid؛
    # از بارگذاری کل جدول در حافظه جلوگیری می‌کند.
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

    # پشتیبان برای زمانی که rowidهای جدول پراکنده باشند.
    if len(selected) < target_count:
        remaining = target_count - len(selected)

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

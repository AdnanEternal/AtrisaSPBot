
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

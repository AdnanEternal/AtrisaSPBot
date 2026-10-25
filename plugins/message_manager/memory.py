
TABLE_NAME = "message_manager_sent_contacts"


async def initialize(db) -> None:
    """ساخت جدول مخاطب‌هایی که پیام را با موفقیت دریافت کرده‌اند."""
    await db.create_table(
        TABLE_NAME,
        {
            "user_id": "INTEGER PRIMARY KEY",
            "sent_at": (
                "TEXT NOT NULL "
                "DEFAULT CURRENT_TIMESTAMP"
            ),
        },
    )


async def get_sent_contact_ids(db) -> set[int]:
    """برگرداندن شناسهٔ تمام مخاطب‌هایی که قبلاً پیام گرفته‌اند."""
    rows = await db.fetchall(
        f"SELECT user_id FROM {TABLE_NAME}"
    )

    return {
        int(row["user_id"])
        for row in rows
    }


async def mark_contact_sent(db, user_id: int) -> None:
    """ثبت مخاطب پس از ارسال موفق پیام."""
    await db.insert(
        TABLE_NAME,
        {
            "user_id": int(user_id),
        },
        or_ignore=True,
    )

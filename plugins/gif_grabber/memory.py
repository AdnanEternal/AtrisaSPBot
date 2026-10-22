import json
import random
import time

TABLE_NAME = "all_saved_gifs"
TAGS_TABLE_NAME = "gif_tags"
SEND_JOBS_TABLE_NAME = "gif_send_jobs"


async def initialize(db) -> None:
    """ساخت بانک گیف‌ها، تگ‌ها و جدول ارسال‌های زمان‌بندی‌شده."""

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

    # وضعیت ارسال‌ها در دیتابیس می‌ماند تا بعد از
    # راه‌اندازی مجدد بتوان آن‌ها را ادامه داد.
    await db.create_table(
        SEND_JOBS_TABLE_NAME,
        columns={
            "job_id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "target_id": "INTEGER NOT NULL",
            "notify_chat_id": "INTEGER NOT NULL DEFAULT 0",
            "gifs_json": "TEXT NOT NULL",
            "interval_seconds": "INTEGER NOT NULL DEFAULT 0",
            "next_index": "INTEGER NOT NULL DEFAULT 0",
            "sent_count": "INTEGER NOT NULL DEFAULT 0",
            "failed_count": "INTEGER NOT NULL DEFAULT 0",
            "next_run_at": "REAL NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "created_at": "REAL NOT NULL",
        },
        indexes=["status"],
    )


async def remember_gif(
    db,
    doc_id: int,
    access_hash: int,
    tags=None,
) -> bool:
    """ثبت گیف و اضافه‌کردن تگ‌های جدید بدون حذف تگ‌های قبلی."""

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
    """تعداد گیف‌ها و پرتکرارترین تگ‌ها."""

    await initialize(db)

    tag_limit = max(0, int(tag_limit))

    total_row = await db.fetchone(
        f"SELECT COUNT(*) AS total FROM {TABLE_NAME}"
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


async def get_random_gifs(
    db,
    count: int,
    tags=None,
) -> list:
    """
    انتخاب گیف‌های تصادفی و یکتا.

    اگر چند تگ داده شود، گیف باید همهٔ آن تگ‌ها را داشته باشد.
    """

    await initialize(db)

    count = max(0, int(count))

    if count == 0:
        return []

    normalized_tags = []
    seen_tags = set()

    for tag in tags or []:
        if not isinstance(tag, str):
            continue

        tag = tag.strip()

        if tag and tag not in seen_tags:
            seen_tags.add(tag)
            normalized_tags.append(tag)

    # انتخاب بر اساس تگ؛ وجود تمام تگ‌های خواسته‌شده الزامی است.
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
            ORDER BY RANDOM()
            LIMIT ?
        """

        return await db.fetchall(
            query,
            tuple(normalized_tags) + (
                len(normalized_tags),
                count,
            ),
        )

    # انتخاب تصادفی بدون تگ؛ روش قبلی حفظ شده است.
    stats = await db.fetchone(
        f"""
        SELECT
            COUNT(*) AS total,
            MAX(rowid) AS max_rowid
        FROM {TABLE_NAME}
        """
    )

    total = stats["total"]
    max_rowid = stats["max_rowid"]

    if not total or not max_rowid:
        return []

    target_count = min(count, int(total))
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
            f"""
            SELECT doc_id, access_hash
            FROM {TABLE_NAME}
            WHERE rowid >= ?
            ORDER BY rowid
            LIMIT 1
            """,
            (row_id,),
        )

        if row is None:
            row = await db.fetchone(
                f"""
                SELECT doc_id, access_hash
                FROM {TABLE_NAME}
                ORDER BY rowid
                LIMIT 1
                """
            )

        if row is not None:
            selected[
                (row["doc_id"], row["access_hash"])
            ] = row

    if len(selected) < target_count:
        rows = await db.fetchall(
            f"""
            SELECT doc_id, access_hash
            FROM {TABLE_NAME}
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (target_count,),
        )

        for row in rows:
            selected[
                (row["doc_id"], row["access_hash"])
            ] = row

            if len(selected) >= target_count:
                break

    return list(selected.values())[:target_count]


async def create_send_job(
    db,
    *,
    target_id: int,
    notify_chat_id: int,
    gifs: list[dict],
    interval_seconds: int,
) -> int:
    """ذخیرهٔ یک کار ارسال جدید."""

    result = await db.insert(
        SEND_JOBS_TABLE_NAME,
        {
            "target_id": int(target_id),
            "notify_chat_id": int(notify_chat_id),
            "gifs_json": json.dumps(
                gifs,
                ensure_ascii=False,
            ),
            "interval_seconds": int(interval_seconds),
            "next_index": 0,
            "sent_count": 0,
            "failed_count": 0,
            "next_run_at": time.time(),
            "status": "active",
            "created_at": time.time(),
        },
    )

    if result.lastrowid is None:
        raise RuntimeError(
            "شناسهٔ کار زمان‌بندی‌شده ایجاد نشد."
        )

    return int(result.lastrowid)


async def get_send_job(db, job_id: int):
    """دریافت یک کار ارسال با شناسه."""

    return await db.fetchone(
        f"""
        SELECT *
        FROM {SEND_JOBS_TABLE_NAME}
        WHERE job_id = ?
        """,
        (int(job_id),),
    )


async def get_active_send_jobs(db) -> list:
    """دریافت تمام کارهای فعال."""

    return await db.fetchall(
        f"""
        SELECT *
        FROM {SEND_JOBS_TABLE_NAME}
        WHERE status = 'active'
        ORDER BY job_id
        """
    )


async def update_send_job(
    db,
    job_id: int,
    **fields,
) -> None:
    """به‌روزرسانی وضعیت و پیشرفت یک کار ارسال."""

    allowed = {
        "next_index",
        "sent_count",
        "failed_count",
        "next_run_at",
        "status",
    }

    if not fields:
        return

    if any(key not in allowed for key in fields):
        raise ValueError(
            "فیلد نامعتبر برای به‌روزرسانی job"
        )

    assignments = ", ".join(
        f"{key} = ?" for key in fields
    )

    params = tuple(fields.values()) + (
        int(job_id),
    )

    await db.execute(
        f"""
        UPDATE {SEND_JOBS_TABLE_NAME}
        SET {assignments}
        WHERE job_id = ?
        """,
        params,
    )


async def cancel_active_send_job(
    db,
    job_id: int,
) -> bool:
    """لغو یک کار، فقط اگر هنوز فعال باشد."""

    result = await db.execute(
        f"""
        UPDATE {SEND_JOBS_TABLE_NAME}
        SET status = 'cancelled'
        WHERE job_id = ?
          AND status = 'active'
        """,
        (int(job_id),),
    )

    return result.rowcount > 0
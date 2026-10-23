import json
import random
import time

TABLE_NAME = "all_saved_gifs"
TAGS_TABLE_NAME = "gif_tags"
SEND_JOBS_TABLE_NAME = "gif_send_jobs"
GIF_CHAT_SETTINGS_TABLE_NAME = "gif_chat_settings"
GIF_SENT_HISTORY_TABLE_NAME = "gif_sent_history"

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

        # تنظیمات مستقل تکرار گیف برای هر مقصد
    await db.create_table(
        GIF_CHAT_SETTINGS_TABLE_NAME,
        columns={
            "chat_id": "INTEGER NOT NULL",
            "allow_repeats": "INTEGER NOT NULL DEFAULT 1",
        },
        unique=[["chat_id"]],
    )

    # سابقهٔ گیف‌هایی که با موفقیت در هر مقصد ارسال شده‌اند
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


async def get_chat_repeats(
    db,
    chat_id: int,
) -> bool:
    """بررسی مجازبودن ارسال گیف تکراری در یک مقصد."""

    await initialize(db)

    row = await db.fetchone(
        f"""
        SELECT allow_repeats
        FROM {GIF_CHAT_SETTINGS_TABLE_NAME}
        WHERE chat_id = ?
        """,
        (int(chat_id),),
    )

    # رفتار پیش‌فرض همان رفتار فعلی است.
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
    """ثبت یک گیف در سابقهٔ ارسال موفق یک مقصد."""

    await initialize(db)

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


async def get_reserved_gifs(
    db,
    chat_id: int,
) -> set[tuple[int, int]]:
    """
    گیف‌های رزروشده برای ارسال‌های فعال یک مقصد را برمی‌گرداند.

    فقط گیف‌هایی که هنوز نوبت ارسالشان نگذشته است رزرو محسوب می‌شوند.
    """

    await initialize(db)

    rows = await db.fetchall(
        f"""
        SELECT next_index, gifs_json
        FROM {SEND_JOBS_TABLE_NAME}
        WHERE target_id = ?
          AND status = 'active'
        """,
        (int(chat_id),),
    )

    reserved = set()

    for row in rows:
        try:
            gifs = json.loads(row["gifs_json"])
            next_index = max(
                0,
                int(row["next_index"] or 0),
            )

        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        if not isinstance(gifs, list):
            continue

        for gif in gifs[next_index:]:
            if not isinstance(gif, dict):
                continue

            try:
                doc_id = int(gif["doc_id"])
                access_hash = int(gif["access_hash"])

            except (KeyError, TypeError, ValueError):
                continue

            reserved.add(
                (doc_id, access_hash)
            )

    return reserved


async def get_random_gifs_for_chat(
    db,
    count: int,
    chat_id: int,
    tags=None,
    reserved_gifs=None,
) -> list:
    """
    انتخاب گیف‌های تصادفی که قبلاً در این مقصد ارسال نشده‌اند
    و برای ارسال فعال دیگری نیز رزرو نشده‌اند.

    در صورت ارسال چند تگ، همهٔ تگ‌های خواسته‌شده باید وجود داشته باشند.
    """

    await initialize(db)

    count = max(0, int(count))

    if count == 0:
        return []

    chat_id = int(chat_id)

    normalized_tags = []
    seen_tags = set()

    for tag in tags or []:
        if not isinstance(tag, str):
            continue

        tag = tag.strip()

        if tag and tag not in seen_tags:
            seen_tags.add(tag)
            normalized_tags.append(tag)

    # فقط گیف‌هایی که در مقصد موردنظر قبلاً ارسال نشده‌اند.
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
            ORDER BY RANDOM()
        """

        params = (
            tuple(normalized_tags)
            + (
                len(normalized_tags),
                chat_id,
            )
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
            ORDER BY RANDOM()
        """

        params = (chat_id,)

    rows = await db.fetchall(
        query,
        params,
    )

    reserved_keys = set(
        reserved_gifs or ()
    )

    selected = []

    for row in rows:
        key = (
            int(row["doc_id"]),
            int(row["access_hash"]),
        )

        if key in reserved_keys:
            continue

        selected.append(row)

        if len(selected) >= count:
            break

    return selected

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
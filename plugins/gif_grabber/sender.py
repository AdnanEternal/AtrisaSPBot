"""ارسال گیف با taskهای موقت و بدون جاب پایدار."""

import asyncio

from splusthon.tl.functions.messages import SendMediaRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from . import memory


async def _resolve_target_peer(
    client,
    target_id: int,
):
    """پیداکردن مقصد از گفتگوهای قابل‌دسترسی."""

    target_id = int(target_id)

    me = await client.get_me()
    my_uid = getattr(me, "id", None)

    if my_uid is not None and target_id == int(my_uid):
        return "me"

    dialogs = await client.get_dialogs()

    for dialog in dialogs:
        dialog_id = int(
            getattr(dialog, "id", 0) or 0
        )

        entity = getattr(dialog, "entity", None)

        entity_id_raw = getattr(
            entity,
            "id",
            None,
        )

        entity_id = (
            int(entity_id_raw)
            if entity_id_raw is not None
            else None
        )

        is_group = bool(
            getattr(dialog, "is_group", False)
        )

        is_channel = bool(
            getattr(dialog, "is_channel", False)
        )

        if dialog_id == target_id:
            return await client.get_input_entity(entity)

        if (
            target_id > 0
            and entity_id == target_id
            and not (is_group or is_channel)
        ):
            return await client.get_input_entity(entity)

        if is_group or is_channel:
            candidates = {
                dialog_id,
                abs(dialog_id),
            }

            if entity_id is not None:
                candidates.update({
                    entity_id,
                    -entity_id,
                    abs(entity_id),
                })

                if is_channel:
                    candidates.add(
                        -int(f"100{entity_id}")
                    )

                    candidates.add(
                        -(1_000_000_000_000 + entity_id)
                    )

            if target_id in candidates:
                return await client.get_input_entity(entity)

    if target_id > 0:
        return await client.get_input_entity(target_id)

    raise ValueError(
        "مقصد منفی در گفتگوهای قابل‌دسترسی پیدا نشد؛ "
        "شناسهٔ گروه یا کانال را بررسی کن."
    )


async def _notify(
    client,
    chat_id: int,
    message: str,
) -> None:
    """ارسال گزارش به گفتگویی که دستور از آن آمده است."""

    if not chat_id:
        print(message)
        return

    try:
        await client.send_message(
            int(chat_id),
            message,
        )

    except Exception as exc:
        print(
            "⚠️ GIF Grabber - ارسال گزارش ناموفق بود: "
            f"{exc}\n{message}"
        )


def get_reserved_gifs(
    self,
    target_id: int,
) -> set[tuple[int, int]]:
    """دریافت گیف‌های رزروشده در ارسال‌های فعال همین اجرا."""

    target_id = int(target_id)

    jobs = getattr(
        self,
        "_gif_send_jobs",
        {},
    )

    reserved = set()

    for job in jobs.values():
        if int(job["target_id"]) != target_id:
            continue

        task = job.get("task")

        if task is None or task.done():
            continue

        next_index = int(job["next_index"])

        for gif in job["gifs"][next_index:]:
            reserved.add((
                int(gif["doc_id"]),
                int(gif["access_hash"]),
            ))

    return reserved


async def start_send_job(
    self,
    *,
    target_id: int,
    notify_chat_id: int,
    gifs: list[dict],
    interval_seconds: int,
    caption: str = "",
) -> int:
    """شروع یک ارسال موقت، بدون ثبت جاب در دیتابیس."""

    await memory.initialize(self.db)

    tasks = getattr(
        self,
        "_gif_send_tasks",
        None,
    )

    if tasks is None:
        tasks = {}
        self._gif_send_tasks = tasks

    jobs = getattr(
        self,
        "_gif_send_jobs",
        None,
    )

    if jobs is None:
        jobs = {}
        self._gif_send_jobs = jobs

    job_id = int(
        getattr(self, "_gif_send_next_id", 1)
    )

    self._gif_send_next_id = job_id + 1

    job = {
        "target_id": int(target_id),
        "notify_chat_id": int(notify_chat_id),
        "gifs": [
            {
                "doc_id": int(gif["doc_id"]),
                "access_hash": int(gif["access_hash"]),
            }
            for gif in gifs
        ],
        "interval_seconds": max(
            0,
            int(interval_seconds),
        ),
        "caption": str(caption),
        "next_index": 0,
        "task": None,
    }

    if not job["gifs"]:
        raise ValueError(
            "فهرست گیف‌های انتخاب‌شده خالی است."
        )

    jobs[job_id] = job

    task = asyncio.create_task(
        _run_send_job(self, job_id),
        name=f"gif-send-{job_id}",
    )

    job["task"] = task
    tasks[job_id] = task

    def remove_finished(
        done_task,
        *,
        current_job_id=job_id,
        current_job=job,
    ):
        if tasks.get(current_job_id) is done_task:
            tasks.pop(current_job_id, None)

        if jobs.get(current_job_id) is current_job:
            jobs.pop(current_job_id, None)

    task.add_done_callback(remove_finished)

    return job_id


async def stop_send_jobs(
    self,
    job_id: int | None = None,
) -> list[int]:
    """
    توقف یک ارسال جاری یا همهٔ ارسال‌های جاری.

    این اطلاعات فقط در حافظه‌اند؛ جابی بعد از ری‌استارت
    برای بازیابی وجود نخواهد داشت.
    """

    jobs = getattr(
        self,
        "_gif_send_jobs",
        {},
    )

    if job_id is None:
        candidates = list(jobs.items())

    else:
        job = jobs.get(int(job_id))

        candidates = (
            [(int(job_id), job)]
            if job is not None
            else []
        )

    stopped_ids = []
    tasks_to_wait = []

    for current_id, job in candidates:
        task = job.get("task")

        if task is None or task.done():
            continue

        stopped_ids.append(int(current_id))
        tasks_to_wait.append(task)
        task.cancel()

    if tasks_to_wait:
        await asyncio.gather(
            *tasks_to_wait,
            return_exceptions=True,
        )

    return stopped_ids


async def shutdown_send_tasks(self) -> None:
    """لغو ارسال‌های جاری هنگام خاموش‌شدن پلاگین."""

    tasks = list(
        getattr(self, "_gif_send_tasks", {}).values()
    )

    for task in tasks:
        if not task.done():
            task.cancel()

    if tasks:
        await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )


async def _run_send_job(
    self,
    job_id: int,
) -> None:
    """اجرای ارسال از فهرست انتخاب‌شده، بدون ذخیرهٔ پیشرفت."""

    jobs = getattr(
        self,
        "_gif_send_jobs",
        {},
    )

    job = jobs.get(int(job_id))

    if job is None:
        return

    target_id = int(job["target_id"])
    notify_chat_id = int(job["notify_chat_id"])
    gifs = job["gifs"]

    interval_seconds = int(
        job["interval_seconds"]
    )
    
    caption = str(
        job.get("caption") or ""
    )

    sent_count = 0
    failed_count = 0

    try:
        target_peer = await _resolve_target_peer(
            self.client,
            target_id,
        )

        for index, gif in enumerate(gifs):
            document_id = int(gif["doc_id"])
            access_hash = int(gif["access_hash"])

            # تا وقتی ارسال موفق یا ناموفق مشخص نشده،
            # گیف جاری در مجموعهٔ رزروشده باقی می‌ماند.
            job["next_index"] = index

            while True:
                try:
                    input_document = types.InputDocument(
                        id=document_id,
                        access_hash=access_hash,
                        file_reference=b"",
                    )

                    await self.client(
                        SendMediaRequest(
                            peer=target_peer,
                            media=types.InputMediaDocument(
                                id=input_document,
                            ),
                            message=caption,
                        )
                    )

                except FloodWaitError as exc:
                    wait_seconds = max(
                        1,
                        int(
                            getattr(exc, "seconds", 1) or 1
                        ),
                    )

                    print(
                        "⚠️ GIF Grabber - محدودیت ارسال؛ "
                        f"گیف {document_id} پس از "
                        f"{wait_seconds} ثانیه دوباره امتحان می‌شود."
                    )

                    await asyncio.sleep(wait_seconds)
                    continue

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    failed_count += 1

                    print(
                        "❌ GIF Grabber - ارسال گیف "
                        f"{document_id} به مقصد {target_id} "
                        f"ناموفق بود (ارسال #{job_id}): {exc}"
                    )

                    break

                else:
                    # ثبت تاریخچه بعد از تأیید موفقیت ارسال
                    try:
                        await memory.remember_sent_gif(
                            self.db,
                            target_id,
                            document_id,
                            access_hash,
                        )

                    except Exception as history_exc:
                        raise RuntimeError(
                            "گیف ارسال شده، اما ثبت سابقهٔ آن "
                            f"ناموفق بود: {document_id}؛ "
                            f"{history_exc}"
                        ) from history_exc

                    sent_count += 1

                    print(
                        f"✅ GIF Grabber - گیف {document_id} "
                        f"به {target_id} ارسال شد "
                        f"(ارسال #{job_id})."
                    )

                    break

            # این گیف دیگر در فهرست رزرو باقی‌مانده نیست.
            job["next_index"] = index + 1

            if (
                interval_seconds > 0
                and index + 1 < len(gifs)
            ):
                await asyncio.sleep(interval_seconds)

        report = (
            f"📤 ارسال گیف تمام شد (شناسهٔ موقت #{job_id}).\n"
            f"🎯 مقصد: {target_id}\n"
            f"🎞️ تعداد انتخاب‌شده: {len(gifs)}\n"
            f"✅ ارسال موفق: {sent_count}\n"
            f"❌ ارسال ناموفق: {failed_count}"
        )

        await _notify(
            self.client,
            notify_chat_id,
            report,
        )

    except asyncio.CancelledError:
        print(
            f"🛑 GIF Grabber - ارسال #{job_id} متوقف شد."
        )
        raise

    except Exception as exc:
        print(
            f"❌ GIF Grabber - ارسال #{job_id} متوقف شد: {exc}"
        )

        report = (
            f"⚠️ ارسال گیف #{job_id} متوقف شد.\n"
            f"🎯 مقصد: {target_id}\n"
            f"✅ ارسال موفق ثبت‌شده: {sent_count}\n"
            f"❌ ارسال ناموفق: {failed_count}\n"
            f"جزئیات: {exc}\n\n"
            "برای تلاش دوباره، دستور ارسال را مجدداً اجرا کن. "
            "گیف‌هایی که در تاریخچه ثبت شده‌اند، در حالت منع "
            "تکرار دوباره انتخاب نخواهند شد."
        )

        await _notify(
            self.client,
            notify_chat_id,
            report,
        )
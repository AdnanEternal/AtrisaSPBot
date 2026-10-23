"""اجرای ارسال‌های زمان‌بندی‌شدهٔ گیف."""

import asyncio
import json
import time

from splusthon.tl.functions.messages import SendMediaRequest
from splusthon.tl import types
from splusthon.errors import FloodWaitError

from . import memory


async def _resolve_target_peer(
    client,
    target_id: int,
):
    """پیداکردن مقصد از گفتگوها با حفظ پشتیبانی از UID قدیمی."""

    target_id = int(target_id)

    me = await client.get_me()
    my_uid = getattr(me, "id", None)

    if (
        my_uid is not None
        and target_id == int(my_uid)
    ):
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

        # حفظ رفتار قبلی برای UIDهایی که در گفتگوها هستند.
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
                    # قالب رایج -100<ID>
                    candidates.add(
                        -int(f"100{entity_id}")
                    )

                    # قالب شناسهٔ کانال SPlusthon
                    candidates.add(
                        -(1_000_000_000_000 + entity_id)
                    )

            if target_id in candidates:
                return await client.get_input_entity(entity)

    # حفظ پشتیبانی از UID خصوصی که در فهرست گفتگوها نیست.
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
    """ارسال گزارش نهایی به گفتگویی که دستور از آن آمده است."""

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
            "⚠️ GIF Grabber - ارسال گزارش job ناموفق بود: "
            f"{exc}\n{message}"
        )


def _spawn(
    self,
    job_id: int,
) -> None:
    """شروع یک کار در پس‌زمینه، بدون اجرای تکراری همان job."""

    tasks = getattr(
        self,
        "_gif_send_tasks",
        None,
    )

    if tasks is None:
        tasks = {}
        self._gif_send_tasks = tasks

    existing = tasks.get(int(job_id))

    if existing is not None and not existing.done():
        return

    task = asyncio.create_task(
        _run_send_job(self, int(job_id)),
        name=f"gif-send-{job_id}",
    )

    tasks[int(job_id)] = task

    def remove_finished(
        done_task,
        *,
        current_job_id=int(job_id),
    ):
        if tasks.get(current_job_id) is done_task:
            tasks.pop(current_job_id, None)

    task.add_done_callback(remove_finished)


async def schedule_send_job(
    self,
    *,
    target_id: int,
    notify_chat_id: int,
    gifs: list[dict],
    interval_seconds: int,
) -> int:
    """ثبت job در دیتابیس و شروع اجرای آن."""

    await memory.initialize(self.db)

    job_id = await memory.create_send_job(
        self.db,
        target_id=target_id,
        notify_chat_id=notify_chat_id,
        gifs=gifs,
        interval_seconds=interval_seconds,
    )

    _spawn(self, job_id)

    return job_id


async def resume_send_jobs(self) -> int:
    """بازیابی کارهای فعال ذخیره‌شده در دیتابیس."""

    await memory.initialize(self.db)

    jobs = await memory.get_active_send_jobs(
        self.db
    )

    for row in jobs:
        _spawn(self, int(row["job_id"]))

    return len(jobs)


async def stop_send_jobs(
    self,
    job_id: int | None = None,
) -> list[int]:
    """توقف یک کار مشخص یا همهٔ کارهای فعال."""

    if job_id is None:
        rows = await memory.get_active_send_jobs(
            self.db
        )
    else:
        row = await memory.get_send_job(
            self.db,
            int(job_id),
        )

        rows = [
            row
        ] if (
            row is not None
            and row["status"] == "active"
        ) else []

    stopped_ids = []

    tasks = getattr(
        self,
        "_gif_send_tasks",
        {},
    )

    for row in rows:
        current_id = int(row["job_id"])

        was_active = await memory.cancel_active_send_job(
            self.db,
            current_id,
        )

        if not was_active:
            continue

        stopped_ids.append(current_id)

        task = tasks.get(current_id)

        if task is not None and not task.done():
            task.cancel()

    return stopped_ids


async def shutdown_send_tasks(self) -> None:
    """
    توقف taskهای فعلی هنگام غیرفعال‌شدن پلاگین.

    وضعیت active در دیتابیس باقی می‌ماند تا هنگام فعال‌شدن مجدد
    پلاگین یا اجرای دوبارهٔ برنامه، کارها قابل بازیابی باشند.
    """

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
    """اجرای یک job؛ هر بار فقط یک گیف ارسال می‌شود."""

    notify_chat_id = 0
    sent_count = 0
    failed_count = 0

    try:
        row = await memory.get_send_job(
            self.db,
            job_id,
        )

        if row is None or row["status"] != "active":
            return

        notify_chat_id = int(
            row["notify_chat_id"] or 0
        )

        target_id = int(row["target_id"])

        interval_seconds = max(
            0,
            int(row["interval_seconds"]),
        )

        sent_count = int(row["sent_count"])
        failed_count = int(row["failed_count"])

        gifs = json.loads(row["gifs_json"])

        if not isinstance(gifs, list) or not gifs:
            raise ValueError(
                "فهرست گیف‌های این job خالی یا نامعتبر است."
            )

        target_peer = None

        while True:
            row = await memory.get_send_job(
                self.db,
                job_id,
            )

            if row is None or row["status"] != "active":
                return

            next_index = int(row["next_index"])

            if next_index >= len(gifs):
                await memory.update_send_job(
                    self.db,
                    job_id,
                    status="completed",
                    next_run_at=0,
                )
                break

            # زمان اجرای بعدی در دیتابیس ذخیره شده است.
            due_at = float(row["next_run_at"] or 0)
            delay = due_at - time.time()

            if delay > 0:
                await asyncio.sleep(delay)

            # ممکن است هنگام انتظار، دستور توقف اجرا شده باشد.
            row = await memory.get_send_job(
                self.db,
                job_id,
            )

            if row is None or row["status"] != "active":
                return

            next_index = int(row["next_index"])

            if next_index >= len(gifs):
                continue

            if target_peer is None:
                target_peer = await _resolve_target_peer(
                    self.client,
                    target_id,
                )

            gif = gifs[next_index]

            document_id = int(gif["doc_id"])
            access_hash = int(gif["access_hash"])

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
                        message="",
                    )
                )

                # این گیف واقعاً ارسال شده است؛
                # قبل از جلو بردن next_index سابقه‌اش را ثبت می‌کنیم.
                try:
                    await memory.remember_sent_gif(
                        self.db,
                        target_id,
                        document_id,
                        access_hash,
                    )

                except Exception as history_exc:
                    # خطای ثبت تاریخچه نباید باعث شود
                    # ارسال موفق را به‌اشتباه ارسال ناموفق بدانیم.
                    print(
                        "❌ GIF Grabber - ثبت سابقهٔ ارسال گیف "
                        f"{document_id} برای مقصد {target_id} ناموفق بود: "
                        f"{history_exc}"
                    )

                sent_count += 1

                print(
                    f"✅ GIF Grabber - گیف {document_id} "
                    f"به {target_id} ارسال شد "
                    f"(job #{job_id})."
                )

                print(
                    f"✅ GIF Grabber - گیف {document_id} "
                    f"به {target_id} ارسال شد "
                    f"(job #{job_id})."
                )

            except FloodWaitError as exc:
                # در صورت محدودیت سرور، همان گیف دوباره امتحان می‌شود
                # پس از گذشت زمان اعلام‌شده.
                wait_seconds = max(
                    1,
                    int(getattr(exc, "seconds", 1) or 1),
                )

                await memory.update_send_job(
                    self.db,
                    job_id,
                    next_run_at=time.time() + wait_seconds,
                )

                print(
                    f"⚠️ GIF Grabber - محدودیت ارسال در "
                    f"job #{job_id}؛ تلاش دوباره پس از "
                    f"{wait_seconds} ثانیه."
                )

                continue

            except Exception as exc:
                failed_count += 1

                print(
                    f"❌ GIF Grabber - ارسال گیف {document_id} "
                    f"به {target_id} ناموفق بود "
                    f"(job #{job_id}): {exc}"
                )

            # پس از هر تلاش، موقعیت بعدی و آمار ذخیره می‌شوند.
            next_index += 1
            completed = next_index >= len(gifs)

            await memory.update_send_job(
                self.db,
                job_id,
                next_index=next_index,
                sent_count=sent_count,
                failed_count=failed_count,
                next_run_at=(
                    time.time() + interval_seconds
                    if not completed
                    else 0
                ),
                status=(
                    "completed"
                    if completed
                    else "active"
                ),
            )

            if completed:
                report = (
                    f"📤 ارسال گیف تمام شد (job #{job_id}).\n"
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

                return

    except asyncio.CancelledError:
        # توقف دستی، وضعیت را قبلاً cancelled می‌کند.
        # در زمان خاموش‌شدن پلاگین، status active می‌ماند
        # تا ارسال بعداً قابل ادامه‌دادن باشد.
        raise

    except Exception as exc:
        print(
            f"❌ GIF Grabber - اجرای job #{job_id} شکست خورد: {exc}"
        )

        try:
            row = await memory.get_send_job(
                self.db,
                job_id,
            )

            if row is not None and row["status"] == "active":
                await memory.update_send_job(
                    self.db,
                    job_id,
                    status="failed",
                )

                notify_chat_id = int(
                    row["notify_chat_id"] or 0
                )

            await _notify(
                self.client,
                notify_chat_id,
                f"❌ ارسال زمان‌بندی‌شدهٔ گیف #{job_id} متوقف شد.\n"
                f"جزئیات: {exc}",
            )

        except Exception as notify_exc:
            print(
                f"⚠️ گزارش خطای job #{job_id} ارسال نشد: "
                f"{notify_exc}"
            )
import os

from celery import Celery
from celery.signals import worker_ready

from docqa.config import get_settings

settings = get_settings()

celery_app = Celery("docqa", broker=settings.redis_url, include=["docqa.services.ingestion"])

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    # No result backend is configured on purpose — Postgres
    # (ingestion_jobs.status) is the single source of truth for job state,
    # not Celery. task_ignore_result makes that explicit rather than
    # accidental.
    task_ignore_result=True,
    # A worker crashing mid-task gets that exact task redelivered to
    # another worker rather than silently dropped — this is what replaces
    # the old poll-based reclaim-on-restart as the primary crash-recovery
    # mechanism (see services/ingestion.py:process_ingestion_job).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Pairs with acks_late: don't let one worker hoard a burst of prefetched
    # tasks ahead of finishing its current one — if it dies, only the task
    # actually in flight needs redelivering, not a whole prefetched batch.
    worker_prefetch_multiplier=1,
)

# Tests set this so `.delay()` runs the task synchronously in-process, with
# no real broker contact — see tests/conftest.py. Mirrors the existing
# pattern of test-only env overrides applied before app imports.
#
# task_eager_propagates is deliberately left False (Celery's own default):
# verified directly (not assumed) that with propagates=False, a self.retry()
# call inside an eager task re-invokes the task synchronously in a loop
# until it stops retrying, and never raises out of .delay() — matching real
# fire-and-forget dispatch, where a caller of .delay() never sees a task's
# internal exceptions either. With propagates=True, retry() instead raises
# straight out of .delay(), which would blow up the upload request itself
# the moment ingestion hit its first transient failure.
if os.environ.get("CELERY_TASK_ALWAYS_EAGER", "").lower() in ("1", "true", "yes"):
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=False)


@worker_ready.connect
def _reclaim_on_startup(**kwargs) -> None:
    """Runs once, when this worker process finishes booting — the Celery
    equivalent of what worker.py used to do before starting its polling
    loop: reset any job left at `processing` from a run that crashed. Kept
    as a defensive backstop alongside acks_late/task_reject_on_worker_lost
    above, for cases where the broker itself lost track of a task rather
    than cleanly redelivering it.
    """
    from docqa.db.session import SessionLocal
    from docqa.services.ingestion import reclaim_stuck_jobs

    db = SessionLocal()
    try:
        reclaim_stuck_jobs(db)
    finally:
        db.close()

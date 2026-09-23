"""Diagnostica e chiude in sicurezza i run di scraping rimasti orfani."""

from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal, _set_next_after_completion


def _task_ids_by_worker() -> tuple[set[str], set[str]]:
    """Restituisce nodi raggiunti e task attivi/riservati/pianificati."""
    inspector = celery_app.control.inspect(timeout=3)
    nodes: set[str] = set()
    task_ids: set[str] = set()
    for snapshot in (inspector.active(), inspector.reserved(), inspector.scheduled()):
        if not snapshot:
            continue
        nodes.update(snapshot)
        for tasks in snapshot.values():
            for task in tasks or []:
                request = task.get("request", task)
                task_id = request.get("id")
                if task_id:
                    task_ids.add(str(task_id))
    return nodes, task_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Individua i run running senza un task presente nei worker Celery."
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Chiude i run orfani; senza questa opzione esegue solo la diagnostica.",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        type=uuid.UUID,
        default=[],
        help="Limita l'operazione a uno o piu ID di run espliciti.",
    )
    args = parser.parse_args()

    nodes, task_ids = _task_ids_by_worker()
    if not nodes:
        raise SystemExit("Nessun worker Celery raggiungibile: riparazione annullata.")

    now = datetime.now(UTC)
    with SyncSessionLocal() as session:
        statement = select(ScrapeRun).where(ScrapeRun.status == "running")
        if args.run_id:
            statement = statement.where(ScrapeRun.id.in_(args.run_id))
        if args.repair:
            statement = statement.with_for_update(skip_locked=True)
        running = session.execute(statement).scalars().all()
        orphaned = [
            run
            for run in running
            if not run.celery_task_id or run.celery_task_id not in task_ids
        ]

        print(f"Worker raggiunti: {len(nodes)}")
        print(f"Run running: {len(running)}")
        print(f"Run orfani: {len(orphaned)}")
        for run in orphaned:
            print(f"- {run.id}")

        if not args.repair:
            print("Diagnostica completata. Usa --repair per chiudere i run elencati.")
            return

        for run in orphaned:
            source = session.get(Source, run.source_id)
            run.status = "failed"
            run.finished_at = now
            run.errors_count += 1
            session.add(
                ScrapeError(
                    scrape_run_id=run.id,
                    url="internal://scrape-run-recovery",
                    error_message="Run interrotto: il task non era presente nei worker Celery.",
                    severity="error",
                )
            )
            if source is not None:
                source.status = "degraded"
                _set_next_after_completion(source, now)
                source.last_schedule_skip_reason = "orphaned_run_closed"
        session.commit()
        print(f"Run chiusi: {len(orphaned)}")


if __name__ == "__main__":
    main()

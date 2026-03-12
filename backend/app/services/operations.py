from app.core.constants import ImportStatus, JobStatus
from app.models.import_job import ImportBatch, Job
from sqlalchemy.orm import Session


def sanitize_jobs_and_imports(db: Session) -> dict[str, int]:
    removed_jobs = (
        db.query(Job)
        .filter(Job.status == JobStatus.DONE, Job.image_id.is_(None))
        .delete(synchronize_session=False)
    )

    updated_imports = 0
    removed_imports = 0
    imports = db.query(ImportBatch).all()
    for import_batch in imports:
        jobs = db.query(Job).filter(Job.import_batch_id == import_batch.id).all()
        if not jobs:
            db.delete(import_batch)
            removed_imports += 1
            continue

        total_files = len(jobs)
        processed_files = sum(1 for job in jobs if job.status == JobStatus.DONE)
        failed_files = sum(1 for job in jobs if job.status == JobStatus.FAILED)
        active_jobs = any(job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING} for job in jobs)

        if (
            import_batch.total_files != total_files
            or import_batch.processed_files != processed_files
            or import_batch.failed_files != failed_files
        ):
            import_batch.total_files = total_files
            import_batch.processed_files = processed_files
            import_batch.failed_files = failed_files
            updated_imports += 1

        next_status = import_batch.status
        if active_jobs:
            next_status = ImportStatus.RUNNING
        elif failed_files:
            next_status = ImportStatus.FAILED
        else:
            next_status = ImportStatus.DONE

        if import_batch.status != next_status:
            import_batch.status = next_status
            updated_imports += 1

        db.add(import_batch)

    return {"removed_jobs": removed_jobs, "updated_imports": updated_imports, "removed_imports": removed_imports}

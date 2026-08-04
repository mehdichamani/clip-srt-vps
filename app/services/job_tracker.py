import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class JobTracker:
    """In-memory job tracking store for bot operations and status visualization."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add_job(
        self,
        job_id: str,
        user_id: Any,
        username: str,
        input_url_or_file: str,
        status: str = "pending"
    ) -> Dict[str, Any]:
        """Creates and stores a new job entry."""
        with self._lock:
            # Enforce max size capacity limit
            if len(self._jobs) >= self.max_size and job_id not in self._jobs:
                # Remove oldest entry based on timestamp
                oldest_job_id = min(self._jobs.keys(), key=lambda k: self._jobs[k].get("timestamp", 0))
                self._jobs.pop(oldest_job_id, None)

            now = time.time()
            iso_time = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            job_record = {
                "job_id": job_id,
                "user_id": str(user_id) if user_id is not None else "Unknown",
                "username": username or "Unknown",
                "input_url_or_file": input_url_or_file or "N/A",
                "status": status,  # pending, processing, done, error, canceled
                "error_message": "",
                "timestamp": now,
                "formatted_time": iso_time,
            }
            self._jobs[job_id] = job_record
            return job_record

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        input_url_or_file: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates an existing job record."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            if status is not None:
                job["status"] = status
            if error_message is not None:
                job["error_message"] = error_message
            if input_url_or_file is not None:
                job["input_url_or_file"] = input_url_or_file

            now = time.time()
            job["updated_at"] = now
            return job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Returns a single job record by ID."""
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_jobs(self) -> List[Dict[str, Any]]:
        """Returns list of all stored jobs, sorted by newest first."""
        with self._lock:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.get("timestamp", 0),
                reverse=True
            )
            return [dict(j) for j in sorted_jobs]

    def get_stats(self) -> Dict[str, int]:
        """Calculates summary statistics of all tracked jobs."""
        with self._lock:
            jobs = list(self._jobs.values())
            total = len(jobs)
            completed = sum(1 for j in jobs if j.get("status") == "done")
            pending_processing = sum(1 for j in jobs if j.get("status") in ("pending", "processing"))
            failed = sum(1 for j in jobs if j.get("status") in ("error", "canceled"))

            return {
                "total": total,
                "completed": completed,
                "pending_processing": pending_processing,
                "failed": failed,
            }


# Global singleton instance of JobTracker
job_tracker = JobTracker(max_size=100)

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("clip_srt_bot")

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 is not installed. JobTracker will operate in in-memory mode.")


class JobTracker:
    """Hybrid job tracking store with PostgreSQL database persistence and in-memory fallback."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._db_initialized = False

    def _normalize_db_url(self) -> Optional[str]:
        """Ensures connection URI uses postgresql:// scheme expected by psycopg2."""
        url = settings.database_url
        if not url:
            return None
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    def init_db(self) -> bool:
        """Initializes PostgreSQL table schema if DATABASE_URL is configured."""
        if not PSYCOPG2_AVAILABLE:
            return False

        db_url = self._normalize_db_url()
        if not db_url:
            logger.info("DATABASE_URL not configured. JobTracker using in-memory mode.")
            return False

        try:
            with psycopg2.connect(db_url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS jobs (
                            job_id VARCHAR(128) PRIMARY KEY,
                            user_id VARCHAR(64) NOT NULL,
                            username VARCHAR(256) NOT NULL,
                            input_url_or_file TEXT NOT NULL,
                            status VARCHAR(32) NOT NULL DEFAULT 'pending',
                            error_message TEXT DEFAULT '',
                            timestamp DOUBLE PRECISION NOT NULL,
                            formatted_time VARCHAR(64) NOT NULL,
                            updated_at DOUBLE PRECISION DEFAULT 0,
                            subject TEXT DEFAULT ''
                        );
                        ALTER TABLE jobs ADD COLUMN IF NOT EXISTS subject TEXT DEFAULT '';
                        CREATE INDEX IF NOT EXISTS idx_jobs_timestamp ON jobs(timestamp DESC);
                    """)
                conn.commit()
            self._db_initialized = True
            logger.info("PostgreSQL database initialized successfully for JobTracker.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database for JobTracker: {e}")
            self._db_initialized = False
            return False

    @property
    def is_db_active(self) -> bool:
        """Returns True if PostgreSQL DB is configured and initialized."""
        return self._db_initialized and bool(self._normalize_db_url())

    def _get_db_connection(self):
        """Helper to return a new PostgreSQL connection if database is active."""
        if not self.is_db_active:
            return None
        db_url = self._normalize_db_url()
        try:
            return psycopg2.connect(db_url, connect_timeout=5)
        except Exception as e:
            logger.error(f"PostgreSQL connection error: {e}")
            return None

    def add_job(
        self,
        job_id: str,
        user_id: Any,
        username: str,
        input_url_or_file: str,
        status: str = "pending",
        subject: str = ""
    ) -> Dict[str, Any]:
        """Creates and stores a new job entry in DB (if active) and in-memory cache."""
        now = time.time()
        iso_time = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        job_record = {
            "job_id": job_id,
            "user_id": str(user_id) if user_id is not None else "Unknown",
            "username": username or "Unknown",
            "input_url_or_file": input_url_or_file or "N/A",
            "status": status,  # pending, processing, done, error, canceled
            "error_message": "",
            "subject": subject or "",
            "timestamp": now,
            "formatted_time": iso_time,
            "updated_at": now,
        }

        # Update in-memory dict
        with self._lock:
            if len(self._jobs) >= self.max_size and job_id not in self._jobs:
                oldest_job_id = min(self._jobs.keys(), key=lambda k: self._jobs[k].get("timestamp", 0))
                self._jobs.pop(oldest_job_id, None)
            self._jobs[job_id] = job_record

        # Persist to PostgreSQL if active
        conn = self._get_db_connection()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO jobs (job_id, user_id, username, input_url_or_file, status, error_message, subject, timestamp, formatted_time, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (job_id) DO UPDATE SET
                                user_id = EXCLUDED.user_id,
                                username = EXCLUDED.username,
                                input_url_or_file = EXCLUDED.input_url_or_file,
                                status = EXCLUDED.status,
                                subject = EXCLUDED.subject,
                                updated_at = EXCLUDED.updated_at;
                        """, (
                            job_record["job_id"],
                            job_record["user_id"],
                            job_record["username"],
                            job_record["input_url_or_file"],
                            job_record["status"],
                            job_record["error_message"],
                            job_record["subject"],
                            job_record["timestamp"],
                            job_record["formatted_time"],
                            job_record["updated_at"],
                        ))
            except Exception as e:
                logger.error(f"Error saving job {job_id} to PostgreSQL: {e}")
            finally:
                conn.close()

        return job_record

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        input_url_or_file: Optional[str] = None,
        subject: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Updates an existing job record in DB (if active) and in-memory cache."""
        now = time.time()

        # Update in-memory dict
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                if status is not None:
                    job["status"] = status
                if error_message is not None:
                    job["error_message"] = error_message
                if input_url_or_file is not None:
                    job["input_url_or_file"] = input_url_or_file
                if subject is not None:
                    job["subject"] = subject
                job["updated_at"] = now

        # Update PostgreSQL if active
        conn = self._get_db_connection()
        if conn:
            try:
                updates = ["updated_at = %s"]
                params: List[Any] = [now]

                if status is not None:
                    updates.append("status = %s")
                    params.append(status)
                if error_message is not None:
                    updates.append("error_message = %s")
                    params.append(error_message)
                if input_url_or_file is not None:
                    updates.append("input_url_or_file = %s")
                    params.append(input_url_or_file)
                if subject is not None:
                    updates.append("subject = %s")
                    params.append(subject)

                params.append(job_id)
                query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = %s"

                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, params)
            except Exception as e:
                logger.error(f"Error updating job {job_id} in PostgreSQL: {e}")
            finally:
                conn.close()

        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Returns a single job record by ID from DB or in-memory fallback."""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
                    row = cur.fetchone()
                    if row:
                        return dict(row)
            except Exception as e:
                logger.error(f"Error fetching job {job_id} from PostgreSQL: {e}")
            finally:
                conn.close()

        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns list of stored jobs (newest first) from DB or in-memory fallback."""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM jobs ORDER BY timestamp DESC LIMIT %s",
                        (limit,)
                    )
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"Error fetching jobs list from PostgreSQL: {e}")
            finally:
                conn.close()

        with self._lock:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.get("timestamp", 0),
                reverse=True
            )
            return [dict(j) for j in sorted_jobs[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """Calculates summary statistics of tracked jobs from DB or in-memory fallback."""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*),
                            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status IN ('pending', 'processing') THEN 1 ELSE 0 END),
                            SUM(CASE WHEN status IN ('error', 'canceled') THEN 1 ELSE 0 END)
                        FROM jobs
                    """)
                    total, completed, pending_proc, failed = cur.fetchone()
                    return {
                        "total": total or 0,
                        "completed": completed or 0,
                        "pending_processing": pending_proc or 0,
                        "failed": failed or 0,
                        "db_active": True,
                    }
            except Exception as e:
                logger.error(f"Error calculating stats from PostgreSQL: {e}")
            finally:
                conn.close()

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
                "db_active": False,
            }

    def get_top_users(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Returns top users with the most request counts from DB or in-memory fallback."""
        conn = self._get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT username, user_id, COUNT(*) as request_count
                        FROM jobs
                        GROUP BY username, user_id
                        ORDER BY request_count DESC, username ASC
                        LIMIT %s
                    """, (limit,))
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"Error fetching top users from PostgreSQL: {e}")
            finally:
                conn.close()

        with self._lock:
            user_counts: Dict[str, Dict[str, Any]] = {}
            for j in self._jobs.values():
                uid = j.get("user_id", "Unknown")
                uname = j.get("username", "Unknown")
                key = f"{uname}_{uid}"
                if key not in user_counts:
                    user_counts[key] = {"username": uname, "user_id": uid, "request_count": 0}
                user_counts[key]["request_count"] += 1

            sorted_users = sorted(user_counts.values(), key=lambda u: u["request_count"], reverse=True)
            return sorted_users[:limit]


# Global singleton instance of JobTracker
job_tracker = JobTracker(max_size=100)

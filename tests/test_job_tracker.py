import unittest
from app.config import settings
from app.services.job_tracker import JobTracker


class TestJobTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = JobTracker(max_size=5)

    def test_in_memory_add_and_get_job(self):
        job = self.tracker.add_job("job-101", 12345, "testuser", "https://example.com/video.mp4")
        self.assertEqual(job["job_id"], "job-101")
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["username"], "testuser")

        retrieved = self.tracker.get_job("job-101")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["job_id"], "job-101")

    def test_in_memory_update_job(self):
        self.tracker.add_job("job-102", 12345, "testuser", "https://example.com/video.mp4")
        updated = self.tracker.update_job("job-102", status="done", error_message="")
        self.assertEqual(updated["status"], "done")

        retrieved = self.tracker.get_job("job-102")
        self.assertEqual(retrieved["status"], "done")

    def test_in_memory_stats(self):
        self.tracker.add_job("job-1", 1, "u1", "f1", status="done")
        self.tracker.add_job("job-2", 2, "u2", "f2", status="processing")
        self.tracker.add_job("job-3", 3, "u3", "f3", status="error")

        stats = self.tracker.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["pending_processing"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertFalse(stats["db_active"])

    def test_normalize_db_url(self):
        old_val = settings.database_url
        try:
            settings.database_url = "postgres://user:pass@host:5432/dbname"
            self.assertEqual(
                self.tracker._normalize_db_url(),
                "postgresql://user:pass@host:5432/dbname"
            )
        finally:
            settings.database_url = old_val


if __name__ == "__main__":
    unittest.main()

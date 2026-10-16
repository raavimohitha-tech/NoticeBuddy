import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import database as db


class NoticeDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(db, "DATABASE_PATH", Path(self.temp_dir.name) / "test.sqlite")
        self.path_patch.start()
        db.initialize()
        self.admin = db.authenticate("admin@noticebuddy.local", "NoticeBuddy123!")
        self.student = db.authenticate("student@noticebuddy.local", "Student123!")
        self.assertIsNotNone(self.admin)
        self.assertIsNotNone(self.student)

    def tearDown(self) -> None:
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_demo_password_is_hashed_and_authentication_checks_it(self) -> None:
        with db.connect() as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                ("student@noticebuddy.local",),
            ).fetchone()["password_hash"]
        self.assertNotEqual(password_hash, "Student123!")
        self.assertIsNone(db.authenticate("student@noticebuddy.local", "incorrect"))

    def test_students_cannot_publish_and_notice_audience_is_filtered(self) -> None:
        with self.assertRaises(PermissionError):
            db.create_notice(self.student, self.notice_values())
        visible = db.list_notices(self.student)
        self.assertTrue(visible)
        self.assertFalse(any(notice["category"] == "Placements" for notice in visible))

    def test_notice_creation_notifies_matching_users_and_supports_read_and_saved_state(self) -> None:
        notice_id = db.create_notice(self.admin, self.notice_values())
        with db.connect() as connection:
            notification = connection.execute(
                "SELECT * FROM notifications WHERE user_id = ? AND kind = 'notice' AND entity_id = ?",
                (self.student["id"], notice_id),
            ).fetchone()
        self.assertIsNotNone(notification)
        notice = db.get_notice(self.student, notice_id)
        self.assertFalse(notice["is_read"])
        self.assertFalse(notice["is_saved"])
        db.mark_notice_read(self.student["id"], notice_id)
        db.toggle_favourite(self.student["id"], notice_id)
        updated = db.get_notice(self.student, notice_id)
        self.assertTrue(updated["is_read"])
        self.assertTrue(updated["is_saved"])

    def test_registration_and_preferences_validate_user_input(self) -> None:
        db.register_user("New Student", "new@college.test", "safe-password-123", "Civil", "3rd Year")
        user = db.authenticate("new@college.test", "safe-password-123")
        self.assertEqual(user["role"], "student")
        db.update_preferences(user["id"], "Civil", "3rd Year", ["Academic"], False)
        updated = db.get_user(user["id"])
        self.assertEqual(updated["categories"], "Academic")
        self.assertFalse(updated["notification_enabled"])
        with self.assertRaises(ValueError):
            db.register_user("Duplicate", "new@college.test", "safe-password-123", "Civil", "3rd Year")

    def test_upcoming_deadline_reminder_is_idempotent(self) -> None:
        values = self.notice_values()
        values["expires_at"] = (date.today() + timedelta(days=1)).isoformat()
        notice_id = db.create_notice(self.admin, values)
        notifications = db.get_notifications(self.student["id"])
        reminder = next(
            item for item in notifications
            if item["kind"] == "deadline" and item["entity_id"] == notice_id
        )
        db.mark_notification_read(self.student["id"], reminder["id"])
        notifications = db.get_notifications(self.student["id"])
        refreshed = next(item for item in notifications if item["id"] == reminder["id"])
        self.assertIsNotNone(refreshed["read_at"])

    def test_administrative_reads_are_role_protected(self) -> None:
        with self.assertRaises(PermissionError):
            db.admin_statistics(self.student)
        with self.assertRaises(PermissionError):
            db.list_users(self.student)

    @staticmethod
    def notice_values() -> dict:
        return {
            "title": "Test notice",
            "description": "Please register before the deadline.",
            "category": "Academic",
            "departments": ["Computer Science"],
            "years": ["2nd Year"],
            "priority": "Important",
            "expires_at": "",
            "pinned": False,
            "published": True,
            "attachment_name": None,
            "attachment_path": None,
            "external_link": "",
        }


if __name__ == "__main__":
    unittest.main()

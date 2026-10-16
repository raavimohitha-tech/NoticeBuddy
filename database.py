import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Generator


DATABASE_PATH = Path(os.getenv("NOTICE_BUDDY_DB", Path(__file__).with_name("noticebuddy.db")))
DEPARTMENTS = ("Computer Science", "Electronics", "Mechanical", "Civil", "Business", "All")
ACADEMIC_YEARS = ("1st Year", "2nd Year", "3rd Year", "4th Year", "All")
CATEGORIES = (
    "Academic",
    "Examinations",
    "Events",
    "Holidays",
    "Placements",
    "Scholarships",
    "Fees",
    "Hostel",
    "Clubs and Activities",
    "General Announcements",
)
PRIORITIES = ("Normal", "Important", "Urgent")


@contextmanager
def connect() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, digest_hex = encoded.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return secrets.compare_digest(candidate.hex(), digest_hex)


def initialize() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'faculty', 'administrator')),
                department TEXT NOT NULL DEFAULT 'Computer Science',
                academic_year TEXT NOT NULL DEFAULT '1st Year',
                categories TEXT NOT NULL DEFAULT '',
                notification_enabled INTEGER NOT NULL DEFAULT 1,
                can_publish INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notices (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                departments TEXT NOT NULL,
                years TEXT NOT NULL,
                priority TEXT NOT NULL,
                published_at TEXT NOT NULL,
                expires_at TEXT,
                author_id INTEGER NOT NULL REFERENCES users(id),
                pinned INTEGER NOT NULL DEFAULT 0,
                published INTEGER NOT NULL DEFAULT 1,
                attachment_name TEXT,
                attachment_path TEXT,
                external_link TEXT,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS notice_reads (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                notice_id INTEGER NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
                read_at TEXT NOT NULL,
                PRIMARY KEY (user_id, notice_id)
            );
            CREATE TABLE IF NOT EXISTS favourites (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                notice_id INTEGER NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, notice_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                venue TEXT NOT NULL,
                category TEXT NOT NULL,
                departments TEXT NOT NULL,
                years TEXT NOT NULL,
                author_id INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_events (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, event_id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT,
                UNIQUE (user_id, kind, entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_notices_published ON notices(published, published_at);
            CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);
            CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at);
            """
        )
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "notification_enabled" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN notification_enabled INTEGER NOT NULL DEFAULT 1"
            )
        now = datetime.now().isoformat(timespec="minutes")
        demo_users = (
            ("Notice Buddy Admin", "admin@noticebuddy.local", "NoticeBuddy123!", "administrator", "Computer Science", "All", 1),
            ("Demo Student", "student@noticebuddy.local", "Student123!", "student", "Computer Science", "2nd Year", 0),
            ("Demo Faculty", "faculty@noticebuddy.local", "Faculty123!", "faculty", "Computer Science", "All", 1),
        )
        for name, email, password, role, department, year, can_publish in demo_users:
            if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                continue
            connection.execute(
                """INSERT INTO users
                   (name, email, password_hash, role, department, academic_year, can_publish, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, email, _hash_password(password), role, department, year, can_publish, now),
            )

        if connection.execute("SELECT COUNT(*) FROM notices").fetchone()[0] == 0:
            admin_id = connection.execute(
                "SELECT id FROM users WHERE email = ?", ("admin@noticebuddy.local",)
            ).fetchone()["id"]
            sample_notices = (
                ("Mid-semester examination timetable", "The mid-semester examinations begin next month. Review the department timetable and arrive at your examination hall 15 minutes early.", "Examinations", "All", "All", "Important", (date.today() + timedelta(days=28)).isoformat(), 1),
                ("Campus technical fest: Nova", "Join student teams for two days of project showcases, coding challenges, workshops, and campus activities. Registration details will be shared by your department.", "Events", "All", "All", "Normal", (date.today() + timedelta(days=12)).isoformat(), 0),
                ("Merit scholarship applications", "Eligible students should submit their scholarship application and supporting documents through the student office before the stated deadline.", "Scholarships", "All", "All", "Urgent", (date.today() + timedelta(days=6)).isoformat(), 1),
                ("College holiday notice", "The campus and administrative offices will remain closed for the upcoming public holiday. Classes resume on the next working day.", "Holidays", "All", "All", "Normal", (date.today() + timedelta(days=18)).isoformat(), 0),
                ("Placement training registration", "Final-year students interested in placement preparation should register with the career services office. Seats are limited.", "Placements", "All", "4th Year", "Important", (date.today() + timedelta(days=9)).isoformat(), 0),
                ("Hostel water-system maintenance", "Scheduled maintenance will temporarily interrupt water service in the north residence block. Please store water in advance.", "Hostel", "All", "All", "Important", (date.today() + timedelta(days=2)).isoformat(), 0),
            )
            for title, description, category, departments, years, priority, expires, pinned in sample_notices:
                connection.execute(
                    """INSERT INTO notices
                       (title, description, category, departments, years, priority, published_at,
                        expires_at, author_id, pinned, published)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (title, description, category, departments, years, priority, now, expires, admin_id, pinned),
                )
        if connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
            admin_id = connection.execute(
                "SELECT id FROM users WHERE email = ?", ("admin@noticebuddy.local",)
            ).fetchone()["id"]
            sample_events = (
                ("Nova technical fest", "Student projects, coding challenges, and hands-on workshops.", 12, "Main campus", "Events", "All", "All"),
                ("Scholarship application closes", "Submit the required application and supporting documents.", 6, "Student office", "Scholarships", "All", "All"),
                ("Placement preparation workshop", "Resume review and interview preparation for final-year students.", 9, "Career services hall", "Placements", "All", "4th Year"),
            )
            for title, description, days, venue, category, departments, years in sample_events:
                connection.execute(
                    """INSERT INTO events
                       (title, description, starts_at, venue, category, departments, years, author_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        title,
                        description,
                        (datetime.now() + timedelta(days=days)).replace(hour=10, minute=0).isoformat(timespec="minutes"),
                        venue,
                        category,
                        departments,
                        years,
                        admin_id,
                        now,
                    ),
                )


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        return None
    user = dict(row)
    user.pop("password_hash")
    return user


def get_user(user_id: int) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("That account no longer exists.")
    user = dict(row)
    user.pop("password_hash")
    return user


def register_user(name: str, email: str, password: str, department: str, academic_year: str) -> None:
    name, email = name.strip(), email.strip().lower()
    if not name or len(name) > 100:
        raise ValueError("Enter a name between 1 and 100 characters.")
    if "@" not in email or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Use a password with at least 8 characters.")
    if department not in DEPARTMENTS or academic_year not in ACADEMIC_YEARS:
        raise ValueError("Choose a valid department and academic year.")
    try:
        with connect() as connection:
            connection.execute(
                """INSERT INTO users
                   (name, email, password_hash, role, department, academic_year, created_at)
                   VALUES (?, ?, ?, 'student', ?, ?, ?)""",
                (name, email, _hash_password(password), department, academic_year, datetime.now().isoformat(timespec="minutes")),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("An account with that email already exists.") from error


def update_preferences(
    user_id: int,
    department: str,
    academic_year: str,
    categories: list[str],
    notification_enabled: bool = True,
) -> None:
    if department not in DEPARTMENTS or academic_year not in ACADEMIC_YEARS:
        raise ValueError("Choose a valid department and academic year.")
    if any(category not in CATEGORIES for category in categories):
        raise ValueError("Choose valid notice categories.")
    with connect() as connection:
        connection.execute(
            """UPDATE users SET department = ?, academic_year = ?, categories = ?,
               notification_enabled = ? WHERE id = ?""",
            (department, academic_year, ",".join(categories), int(notification_enabled), user_id),
        )


def _matches_audience(row: sqlite3.Row, user: dict[str, Any]) -> bool:
    departments = {item.strip() for item in row["departments"].split(",")}
    years = {item.strip() for item in row["years"].split(",")}
    return (
        ("All" in departments or user["department"] in departments)
        and ("All" in years or user["academic_year"] in years)
    )


def _check_notice_access(connection: sqlite3.Connection, user_id: int, notice_id: int) -> None:
    row = connection.execute(
        """SELECT n.published, n.archived, n.departments, n.years, u.role, u.department, u.academic_year
           FROM notices n JOIN users u ON u.id = ? WHERE n.id = ?""",
        (user_id, notice_id),
    ).fetchone()
    if row is None or not row["published"] or row["archived"] or not _matches_audience(row, row):
        raise PermissionError("This notice is not available to your account.")


def list_notices(user: dict[str, Any], search: str = "", category: str = "All", priority: str = "All",
                 view: str = "All notices", sort: str = "Newest", include_expired: bool = False) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT n.*, u.name AS author,
                      EXISTS(SELECT 1 FROM notice_reads r WHERE r.notice_id = n.id AND r.user_id = ?) AS is_read,
                      EXISTS(SELECT 1 FROM favourites f WHERE f.notice_id = n.id AND f.user_id = ?) AS is_saved
               FROM notices n JOIN users u ON u.id = n.author_id
               WHERE n.published = 1 AND n.archived = 0
               ORDER BY n.pinned DESC, n.published_at DESC""",
            (user["id"], user["id"]),
        ).fetchall()
    today = date.today().isoformat()
    results = []
    relevant_categories = set(filter(None, user["categories"].split(",")))
    for row in rows:
        item = dict(row)
        if not _matches_audience(row, user):
            continue
        expired = bool(item["expires_at"] and item["expires_at"] < today)
        if expired and not include_expired:
            continue
        if category not in ("All", "All categories") and item["category"] != category:
            continue
        if priority not in ("All", "All priorities") and item["priority"] != priority:
            continue
        if search.casefold() not in f"{item['title']} {item['description']} {item['category']}".casefold():
            continue
        if view == "Unread" and item["is_read"]:
            continue
        if view == "Pinned" and not item["pinned"]:
            continue
        if view == "Saved" and not item["is_saved"]:
            continue
        if view == "Urgent" and item["priority"] != "Urgent":
            continue
        if view == "Recommended" and relevant_categories and item["category"] not in relevant_categories:
            continue
        item["expired"] = expired
        results.append(item)
    if sort == "Oldest":
        results.sort(key=lambda notice: notice["published_at"])
        results.sort(key=lambda notice: bool(notice["pinned"]), reverse=True)
    elif sort == "Priority":
        priority_order = {"Urgent": 0, "Important": 1, "Normal": 2}
        results.sort(key=lambda notice: (not notice["pinned"], priority_order[notice["priority"]], notice["published_at"]))
    else:
        results.sort(key=lambda notice: notice["published_at"], reverse=True)
        results.sort(key=lambda notice: bool(notice["pinned"]), reverse=True)
    return results


def get_notice(user: dict[str, Any], notice_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """SELECT n.*, u.name AS author,
                      EXISTS(SELECT 1 FROM notice_reads r WHERE r.notice_id = n.id AND r.user_id = ?) AS is_read,
                      EXISTS(SELECT 1 FROM favourites f WHERE f.notice_id = n.id AND f.user_id = ?) AS is_saved
               FROM notices n JOIN users u ON u.id = n.author_id WHERE n.id = ?""",
            (user["id"], user["id"], notice_id),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    permitted = user["role"] == "administrator" or item["author_id"] == user["id"] or (
        item["published"] and _matches_audience(row, user)
    )
    return item if permitted else None


def mark_notice_read(user_id: int, notice_id: int) -> None:
    with connect() as connection:
        _check_notice_access(connection, user_id, notice_id)
        connection.execute(
            "INSERT OR IGNORE INTO notice_reads (user_id, notice_id, read_at) VALUES (?, ?, ?)",
            (user_id, notice_id, datetime.now().isoformat(timespec="minutes")),
        )


def toggle_favourite(user_id: int, notice_id: int) -> None:
    with connect() as connection:
        _check_notice_access(connection, user_id, notice_id)
        existing = connection.execute(
            "SELECT 1 FROM favourites WHERE user_id = ? AND notice_id = ?", (user_id, notice_id)
        ).fetchone()
        if existing:
            connection.execute("DELETE FROM favourites WHERE user_id = ? AND notice_id = ?", (user_id, notice_id))
        else:
            connection.execute(
                "INSERT INTO favourites (user_id, notice_id, created_at) VALUES (?, ?, ?)",
                (user_id, notice_id, datetime.now().isoformat(timespec="minutes")),
            )


def _can_publish(user: dict[str, Any]) -> bool:
    return user["role"] == "administrator" or (user["role"] == "faculty" and user["can_publish"])


def _validate_notice(user: dict[str, Any], title: str, description: str, category: str,
                     departments: list[str], years: list[str], priority: str, expires_at: str | None) -> None:
    if not _can_publish(user):
        raise PermissionError("Only administrators and authorised faculty can publish notices.")
    if not title.strip() or len(title) > 180:
        raise ValueError("Enter a notice title between 1 and 180 characters.")
    if not description.strip() or len(description) > 20_000:
        raise ValueError("Enter a notice description of up to 20,000 characters.")
    if category not in CATEGORIES or priority not in PRIORITIES:
        raise ValueError("Choose a valid category and priority.")
    if not departments or any(item not in DEPARTMENTS for item in departments):
        raise ValueError("Choose at least one valid department.")
    if not years or any(item not in ACADEMIC_YEARS for item in years):
        raise ValueError("Choose at least one valid academic year.")
    if expires_at:
        try:
            date.fromisoformat(expires_at)
        except ValueError as error:
            raise ValueError("Enter a valid expiry date.") from error


def _notify_targeted_users(connection: sqlite3.Connection, kind: str, entity_id: int,
                           message: str, departments: str, years: str, category: str) -> None:
    users = connection.execute(
        "SELECT id, department, academic_year, categories, notification_enabled FROM users"
    ).fetchall()
    dept_set, year_set = set(departments.split(",")), set(years.split(","))
    now = datetime.now().isoformat(timespec="minutes")
    for user in users:
        category_preferences = set(filter(None, user["categories"].split(",")))
        matches_category = not category_preferences or kind != "notice" or category in category_preferences
        if user["notification_enabled"] and matches_category and ("All" in dept_set or user["department"] in dept_set) and (
            "All" in year_set or user["academic_year"] in year_set
        ):
            connection.execute(
                """INSERT INTO notifications (user_id, kind, entity_id, message, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, kind, entity_id) DO UPDATE SET
                   message = excluded.message, created_at = excluded.created_at, read_at = NULL""",
                (user["id"], kind, entity_id, message, now),
            )


def create_notice(user: dict[str, Any], values: dict[str, Any]) -> int:
    _validate_notice(
        user, values["title"], values["description"], values["category"], values["departments"],
        values["years"], values["priority"], values["expires_at"],
    )
    with connect() as connection:
        cursor = connection.execute(
            """INSERT INTO notices
               (title, description, category, departments, years, priority, published_at, expires_at,
                author_id, pinned, published, attachment_name, attachment_path, external_link)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["title"].strip(), values["description"].strip(), values["category"],
                ",".join(values["departments"]), ",".join(values["years"]), values["priority"],
                datetime.now().isoformat(timespec="minutes"), values["expires_at"] or None, user["id"],
                int(values["pinned"]), int(values["published"]), values.get("attachment_name"),
                values.get("attachment_path"), values["external_link"].strip() or None,
            ),
        )
        notice_id = int(cursor.lastrowid)
        if values["published"]:
            _notify_targeted_users(
                connection, "notice", notice_id, f"New {values['priority'].lower()} notice: {values['title'].strip()}",
                ",".join(values["departments"]), ",".join(values["years"]), values["category"],
            )
    return notice_id


def update_notice(user: dict[str, Any], notice_id: int, values: dict[str, Any]) -> None:
    _validate_notice(
        user, values["title"], values["description"], values["category"], values["departments"],
        values["years"], values["priority"], values["expires_at"],
    )
    with connect() as connection:
        current = connection.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if current is None:
            raise ValueError("That notice no longer exists.")
        if user["role"] != "administrator" and current["author_id"] != user["id"]:
            raise PermissionError("You may edit only notices you published.")
        connection.execute(
            """UPDATE notices SET title = ?, description = ?, category = ?, departments = ?, years = ?,
               priority = ?, expires_at = ?, pinned = ?, published = ?, external_link = ? WHERE id = ?""",
            (
                values["title"].strip(), values["description"].strip(), values["category"],
                ",".join(values["departments"]), ",".join(values["years"]), values["priority"],
                values["expires_at"] or None, int(values["pinned"]), int(values["published"]),
                values["external_link"].strip() or None, notice_id,
            ),
        )
        if values["published"]:
            _notify_targeted_users(
                connection, "notice", notice_id, f"Notice updated: {values['title'].strip()}",
                ",".join(values["departments"]), ",".join(values["years"]), values["category"],
            )


def archive_notice(user: dict[str, Any], notice_id: int) -> None:
    with connect() as connection:
        row = connection.execute("SELECT author_id FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if row is None:
            raise ValueError("That notice no longer exists.")
        if user["role"] != "administrator" and row["author_id"] != user["id"]:
            raise PermissionError("You may archive only notices you published.")
        connection.execute("UPDATE notices SET archived = 1 WHERE id = ?", (notice_id,))


def delete_notice(user: dict[str, Any], notice_id: int) -> str | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT author_id, attachment_path FROM notices WHERE id = ?", (notice_id,)
        ).fetchone()
        if row is None:
            raise ValueError("That notice no longer exists.")
        if user["role"] != "administrator" and row["author_id"] != user["id"]:
            raise PermissionError("You may delete only notices you published.")
        attachment_path = row["attachment_path"]
        connection.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    return attachment_path


def list_events(user: dict[str, Any]) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """SELECT e.*, u.name AS author,
                      EXISTS(SELECT 1 FROM saved_events s WHERE s.event_id = e.id AND s.user_id = ?) AS is_saved
               FROM events e JOIN users u ON u.id = e.author_id ORDER BY e.starts_at""",
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows if _matches_audience(row, user)]


def create_event(user: dict[str, Any], values: dict[str, Any]) -> int:
    if not _can_publish(user):
        raise PermissionError("Only administrators and authorised faculty can publish events.")
    if not values["title"].strip() or not values["description"].strip() or not values["venue"].strip():
        raise ValueError("Add an event title, description, and venue.")
    try:
        starts_at = datetime.fromisoformat(values["starts_at"])
    except ValueError as error:
        raise ValueError("Enter a valid event date and time.") from error
    if values["category"] not in CATEGORIES or not values["departments"] or not values["years"]:
        raise ValueError("Choose a valid event category, department, and year.")
    with connect() as connection:
        cursor = connection.execute(
            """INSERT INTO events
               (title, description, starts_at, venue, category, departments, years, author_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                values["title"].strip(), values["description"].strip(), starts_at.isoformat(timespec="minutes"),
                values["venue"].strip(), values["category"], ",".join(values["departments"]),
                ",".join(values["years"]), user["id"], datetime.now().isoformat(timespec="minutes"),
            ),
        )
        event_id = int(cursor.lastrowid)
        _notify_targeted_users(
            connection, "event", event_id, f"Campus event: {values['title'].strip()}",
            ",".join(values["departments"]), ",".join(values["years"]), values["category"],
        )
    return event_id


def toggle_saved_event(user_id: int, event_id: int) -> None:
    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM saved_events WHERE user_id = ? AND event_id = ?", (user_id, event_id)
        ).fetchone()
        if exists:
            connection.execute("DELETE FROM saved_events WHERE user_id = ? AND event_id = ?", (user_id, event_id))
        else:
            connection.execute("INSERT INTO saved_events (user_id, event_id) VALUES (?, ?)", (user_id, event_id))


def get_notifications(user_id: int) -> list[dict[str, Any]]:
    refresh_reminders(user_id)
    with connect() as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user_id,)
            ).fetchall()
        ]


def refresh_reminders(user_id: int) -> None:
    now = datetime.now()
    deadline_limit = (now.date() + timedelta(days=3)).isoformat()
    event_limit = (now + timedelta(days=3)).isoformat(timespec="minutes")
    with connect() as connection:
        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            raise ValueError("That account no longer exists.")
        if not user["notification_enabled"]:
            return
        categories = set(filter(None, user["categories"].split(",")))
        notices = connection.execute(
            """SELECT id, title, expires_at, category, departments, years FROM notices
               WHERE published = 1 AND archived = 0 AND expires_at >= ? AND expires_at <= ?""",
            (now.date().isoformat(), deadline_limit),
        ).fetchall()
        for notice in notices:
            if categories and notice["category"] not in categories:
                continue
            if not _matches_audience(notice, user):
                continue
            connection.execute(
                """INSERT OR IGNORE INTO notifications
                   (user_id, kind, entity_id, message, created_at) VALUES (?, 'deadline', ?, ?, ?)""",
                (
                    user_id,
                    notice["id"],
                    f"Upcoming deadline: {notice['title']} (expires {notice['expires_at']})",
                    now.isoformat(timespec="minutes"),
                ),
            )
        events = connection.execute(
            """SELECT id, title, starts_at, departments, years FROM events
               WHERE starts_at >= ? AND starts_at <= ?""",
            (now.isoformat(timespec="minutes"), event_limit),
        ).fetchall()
        for event in events:
            if not _matches_audience(event, user):
                continue
            connection.execute(
                """INSERT OR IGNORE INTO notifications
                   (user_id, kind, entity_id, message, created_at) VALUES (?, 'event_reminder', ?, ?, ?)""",
                (
                    user_id,
                    event["id"],
                    f"Coming up: {event['title']} on {event['starts_at']}",
                    now.isoformat(timespec="minutes"),
                ),
            )


def mark_notification_read(user_id: int, notification_id: int) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL",
            (datetime.now().isoformat(timespec="minutes"), notification_id, user_id),
        )


def admin_statistics(user: dict[str, Any]) -> dict[str, Any]:
    if user["role"] != "administrator":
        raise PermissionError("Only administrators can view the publishing overview.")
    with connect() as connection:
        return {
            "published": connection.execute("SELECT COUNT(*) FROM notices WHERE published = 1 AND archived = 0").fetchone()[0],
            "drafts": connection.execute("SELECT COUNT(*) FROM notices WHERE published = 0 AND archived = 0").fetchone()[0],
            "events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "users": connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "recent": [
                dict(row) for row in connection.execute(
                    """SELECT n.id, n.title, n.priority, n.published_at, n.published, u.name AS author
                       FROM notices n JOIN users u ON u.id = n.author_id ORDER BY n.published_at DESC LIMIT 5"""
                ).fetchall()
            ],
            "notices": [
                dict(row) for row in connection.execute(
                    """SELECT n.id, n.title, n.priority, n.published_at, n.expires_at, n.published, n.archived,
                              n.pinned, n.author_id, n.attachment_path, u.name AS author
                       FROM notices n JOIN users u ON u.id = n.author_id ORDER BY n.published_at DESC"""
                ).fetchall()
            ],
        }


def publisher_statistics(user: dict[str, Any]) -> dict[str, Any]:
    if not _can_publish(user):
        raise PermissionError("Your account is not authorised to view publishing activity.")
    if user["role"] == "administrator":
        return admin_statistics(user)
    with connect() as connection:
        notices = [
            dict(row) for row in connection.execute(
                """SELECT n.id, n.title, n.priority, n.published_at, n.expires_at, n.published, n.archived,
                          n.pinned, n.author_id, n.attachment_path, u.name AS author
                   FROM notices n JOIN users u ON u.id = n.author_id
                   WHERE n.author_id = ? ORDER BY n.published_at DESC""",
                (user["id"],),
            ).fetchall()
        ]
        event_count = connection.execute("SELECT COUNT(*) FROM events WHERE author_id = ?", (user["id"],)).fetchone()[0]
    return {
        "published": sum(item["published"] and not item["archived"] for item in notices),
        "drafts": sum(not item["published"] and not item["archived"] for item in notices),
        "events": event_count,
        "users": None,
        "notices_created": len(notices),
        "recent": notices[:5],
        "notices": notices,
    }


def list_users(user: dict[str, Any]) -> list[dict[str, Any]]:
    if user["role"] != "administrator":
        raise PermissionError("Only administrators can view account management.")
    with connect() as connection:
        return [
            dict(row) for row in connection.execute(
                """SELECT id, name, email, role, department, academic_year, can_publish
                   FROM users ORDER BY role, name"""
            ).fetchall()
        ]


def authorize_faculty(user: dict[str, Any], faculty_id: int, allowed: bool) -> None:
    if user["role"] != "administrator":
        raise PermissionError("Only administrators can authorise faculty publishers.")
    with connect() as connection:
        connection.execute(
            "UPDATE users SET can_publish = ? WHERE id = ? AND role = 'faculty'",
            (int(allowed), faculty_id),
        )

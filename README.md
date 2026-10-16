# Notice Buddy

Notice Buddy is a local Streamlit campus communication app for notices, events, deadlines, and notice-text assistance. It extends the original image OCR prototype and uses SQLite so the demo works without a separate backend service.

## Run locally on Windows

From the project folder in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

To create a fresh virtual environment if `.venv` is missing:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app creates `noticebuddy.db` and an `uploads` folder in the project directory the first time it starts. Set `NOTICE_BUDDY_DB` to use another SQLite file location.

## Local demo accounts

These accounts and their sample content are for local demonstration only:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | `admin@noticebuddy.local` | `NoticeBuddy123!` |
| Student | `student@noticebuddy.local` | `Student123!` |
| Authorised faculty | `faculty@noticebuddy.local` | `Faculty123!` |

Passwords are stored as salted PBKDF2 hashes. New registrations receive the student role. An administrator must explicitly grant publishing permission to other faculty accounts. Do not expose the demo accounts or this local Streamlit configuration on a public network.

## Included features

- Student registration and sign-in, role-gated publishing, and administrator-managed faculty permissions.
- SQLite persistence for notices, audience targeting, favourites, read receipts, events, saved events, user preferences, and in-app notifications, with deadline/event reminders generated when a signed-in user opens notifications.
- Notice search, category/priority filters, unread/pinned/saved/urgent views, sorting, expiry labels, drafts, publishing, pinning, archiving, and confirmed deletion.
- Publisher dashboard, notice editor, campus event and deadline creation, monthly calendar, and upcoming event list.
- Profile preferences, category-based recommendations and notification controls.
- PDF/PNG/JPEG attachments (up to 5 MB), stored using generated filenames and available to users who can access the notice.
- Local extractive notice assistance: OCR for uploaded images and selection of likely dates/action lines. It does not call a hosted AI service and does not guarantee that extracted information is complete.
- Responsive Streamlit layout, dark appearance toggle, and clearly labelled fictional sample notices.

## Optional OCR setup

Image text extraction requires Tesseract OCR in addition to the Python dependencies. The app checks `C:\Program Files\Tesseract-OCR\tesseract.exe` automatically. If Tesseract is installed elsewhere, update `TESSERACT_PATH` in `app.py`. Without Tesseract, text pasted into the assistant remains available and image upload reports that OCR is unavailable.

## Validation

Run the focused database and permission tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Scope and deployment notes

Email, browser push, mobile notifications, hosted AI summaries, and institution-specific identity-provider login are not configured. Notifications in this version are in-app only; deadline/event reminders are refreshed when a user visits the app rather than by a background scheduler. The included Streamlit configuration binds the demo server to `127.0.0.1`. Before any real deployment, replace demo accounts, use HTTPS and a production-grade authentication/session design, review upload storage and retention, configure secrets and backups, and obtain the institution's approval for official announcements.

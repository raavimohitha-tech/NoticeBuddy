import calendar
import html
import io
import os
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytesseract
import streamlit as st
from PIL import Image, UnidentifiedImageError

import database as db


st.set_page_config(page_title="Notice Buddy", page_icon="📢", layout="wide")
db.initialize()

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

st.markdown(
    """
    <style>
    :root { --ink:#0b1220; --muted:#64748b; --blue:#3b82f6; --cyan:#22d3ee; }
    html, body, [class*="css"] { font-family:'DM Sans','Segoe UI',sans-serif; }
    .stApp { background:linear-gradient(135deg,#f8fafc 0%,#eef4fb 55%,#f1f5f9 100%); color:#0b1220; }
    h1,h2,h3 { font-family:'Manrope',sans-serif; letter-spacing:-.035em; color:#0b1220; }
    [data-testid="stSidebar"] { background:#0b1220; }
    [data-testid="stSidebar"] * { color:#e2e8f0; }
    [data-testid="stSidebar"] button { border-radius:12px; }
    .hero { padding:2.4rem 2.5rem; border-radius:28px; color:#f8fafc;
      background:radial-gradient(circle at 82% 8%,rgba(34,211,238,.3),transparent 25%),
      linear-gradient(120deg,#0b1220,#151f32 66%,#193b67); box-shadow:0 22px 60px rgba(15,23,42,.18); }
    .hero h1 { font-size:clamp(2.25rem,5vw,4rem); line-height:1.08; color:#f8fafc; margin:.5rem 0 1rem; }
    .hero p { color:#cbd5e1; font-size:1.08rem; max-width:620px; }
    .eyebrow { color:#67e8f9; text-transform:uppercase; letter-spacing:.16em; font-size:.78rem; font-weight:700; }
    .metric { border:1px solid rgba(148,163,184,.25); background:rgba(255,255,255,.92); border-radius:18px;
      padding:1.15rem 1.25rem; box-shadow:0 8px 26px rgba(15,23,42,.055); min-height:116px; }
    .metric-label { color:#64748b; font-size:.86rem; font-weight:600; }
    .metric-value { color:#0b1220; font:800 1.8rem 'Manrope',sans-serif; margin-top:.25rem; }
    .metric-detail { color:#64748b; font-size:.8rem; margin-top:.15rem; }
    .notice-card { padding:1.15rem 1.25rem; margin:.7rem 0; background:#fff; border:1px solid #e2e8f0;
      border-radius:18px; box-shadow:0 8px 24px rgba(15,23,42,.045); transition:transform .16s ease,box-shadow .16s ease; }
    .notice-card:hover { transform:translateY(-2px); box-shadow:0 14px 30px rgba(15,23,42,.09); }
    .notice-meta { color:#64748b; font-size:.83rem; }
    .pill { display:inline-block; border-radius:99px; padding:.2rem .62rem; margin-right:.35rem;
      font-size:.72rem; font-weight:700; background:#eff6ff; color:#1d4ed8; }
    .urgent { background:#fff1f2; color:#be123c; }
    .important { background:#fff7ed; color:#c2410c; }
    .normal { background:#ecfdf5; color:#047857; }
    .section-label { color:#64748b; font-size:.82rem; letter-spacing:.1em; font-weight:700; text-transform:uppercase; }
    .soft-panel { background:#fff; border:1px solid #e2e8f0; border-radius:20px; padding:1.3rem; }
    div[data-testid="stForm"] { border:1px solid #e2e8f0; border-radius:18px; background:white; padding:1.2rem; }
    .stButton>button, .stFormSubmitButton>button { border-radius:12px; font-weight:700; }
    footer { visibility:hidden; }
    @media(max-width:700px) { .hero {padding:1.5rem;border-radius:20px;} }
    </style>
    """,
    unsafe_allow_html=True,
)
if st.session_state.get("dark_mode"):
    st.markdown(
        """
        <style>
        .stApp { background:#0b1220; color:#e2e8f0; }
        h1,h2,h3 { color:#f8fafc; }
        [data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li { color:#cbd5e1; }
        .metric,.notice-card,.soft-panel,div[data-testid="stForm"] { background:#151f32; border-color:#334155; }
        .metric-value,.notice-card h3 { color:#f8fafc !important; }
        .metric-label,.metric-detail,.notice-meta { color:#94a3b8; }
        .notice-card p { color:#cbd5e1 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _is_publisher(user: dict) -> bool:
    return user["role"] == "administrator" or (user["role"] == "faculty" and user["can_publish"])


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _safe_attachment(uploaded_file) -> tuple[str | None, str | None]:
    if uploaded_file is None:
        return None, None
    data = uploaded_file.getvalue()
    extension = Path(uploaded_file.name).suffix.lower()
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Attachments must be 5 MB or smaller.")
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("That file does not appear to be a valid PDF.")
    elif extension in {".png", ".jpg", ".jpeg"}:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("That image could not be verified. Please choose a valid PNG or JPEG.") from error
    else:
        raise ValueError("Only PDF, PNG, and JPEG attachments are permitted.")
    upload_dir = Path(__file__).with_name("uploads")
    upload_dir.mkdir(exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{extension}"
    destination = upload_dir / safe_name
    destination.write_bytes(data)
    return Path(uploaded_file.name).name[:120], str(destination)


def _remove_attachment(path: str | None) -> None:
    if not path:
        return
    resolved = Path(path).resolve()
    upload_root = Path(__file__).with_name("uploads").resolve()
    if resolved.parent == upload_root and resolved.is_file():
        resolved.unlink()


def _insights(text: str) -> dict[str, list[str]]:
    normalized = re.sub(r"\s+", " ", text).strip()
    date_pattern = (
        r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?)\b"
    )
    dates = list(dict.fromkeys(re.findall(date_pattern, text, flags=re.IGNORECASE)))
    lines = [re.sub(r"\s+", " ", line).strip(" •-\t") for line in text.splitlines() if line.strip()]
    if not lines and normalized:
        lines = [normalized]
    action_words = ("submit", "exam", "fee", "deadline", "register", "registration", "attendance",
                    "bring", "report", "apply", "application", "must", "required")
    actions = [line for line in lines if any(word in line.casefold() for word in action_words)]
    summary = lines[:3]
    return {"summary": summary, "dates": dates, "actions": list(dict.fromkeys(actions[:8]))}


def _metric(label: str, value: str | int, detail: str = "") -> None:
    st.markdown(
        f'<div class="metric"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-detail">{detail}</div></div>',
        unsafe_allow_html=True,
    )


def _notice_card(notice: dict, key_prefix: str = "notice") -> None:
    priority_class = notice["priority"].lower()
    extras = []
    if notice["pinned"]:
        extras.append('<span class="pill">PINNED</span>')
    extras.append(f'<span class="pill {priority_class}">{notice["priority"].upper()}</span>')
    extras.append(f'<span class="pill">{_escape(notice["category"])}</span>')
    if notice.get("expired"):
        extras.append('<span class="pill urgent">EXPIRED</span>')
    if not notice["is_read"]:
        extras.append('<span class="pill">UNREAD</span>')
    st.markdown(
        f'<div class="notice-card"><div>{" ".join(extras)}</div>'
        f'<h3 style="margin:.7rem 0 .25rem">{_escape(notice["title"])}</h3>'
        f'<div class="notice-meta">By {_escape(notice["author"])} · {_escape(notice["published_at"][:10])}'
        f'{" · Expires " + _escape(notice["expires_at"]) if notice["expires_at"] else ""}</div>'
        f'<p style="margin:.75rem 0 0;color:#334155">{_escape(notice["description"][:240])}'
        f'{"…" if len(notice["description"]) > 240 else ""}</p></div>',
        unsafe_allow_html=True,
    )
    columns = st.columns([1, 1, 5])
    with columns[0]:
        if st.button("Open", key=f"{key_prefix}_open_{notice['id']}", use_container_width=True):
            st.session_state.selected_notice_id = notice["id"]
            st.query_params["notice"] = str(notice["id"])
            st.rerun()
    with columns[1]:
        button_text = "Saved" if notice["is_saved"] else "Save"
        if st.button(button_text, key=f"{key_prefix}_save_{notice['id']}", use_container_width=True):
            db.toggle_favourite(st.session_state.user["id"], notice["id"])
            st.rerun()


def _render_notice_detail(user: dict) -> bool:
    notice_id = st.session_state.get("selected_notice_id")
    if notice_id is None:
        return False
    notice = db.get_notice(user, int(notice_id))
    if notice is None:
        st.error("This notice is no longer available to your account.")
        st.session_state.pop("selected_notice_id", None)
        return False
    if user["role"] != "administrator" and notice["published"]:
        db.mark_notice_read(user["id"], notice["id"])
    if st.button("← Back to notices", key="back_to_notices"):
        st.session_state.pop("selected_notice_id", None)
        st.query_params.pop("notice", None)
        st.rerun()
    st.markdown(f"## {notice['title']}")
    st.caption(f"{notice['category']} · {notice['priority']} · Published {notice['published_at']}")
    st.markdown(notice["description"])
    st.caption(f"Audience: {notice['departments'].replace(',', ', ')} · {notice['years'].replace(',', ', ')}")
    if notice["expires_at"]:
        st.caption(f"Expiry date: {notice['expires_at']}")
    if notice["external_link"]:
        st.link_button("Open related link", notice["external_link"])
    port = st.get_option("server.port")
    base_path = st.get_option("server.baseUrlPath").strip("/")
    share_path = f"/{base_path}" if base_path else ""
    st.text_input(
        "Shareable link (local demo)",
        value=f"http://127.0.0.1:{port}{share_path}/?notice={notice['id']}",
        disabled=True,
        key=f"share_notice_{notice['id']}",
    )
    if notice["attachment_path"] and Path(notice["attachment_path"]).is_file():
        st.download_button(
            f"Download {notice['attachment_name'] or 'attachment'}",
            data=Path(notice["attachment_path"]).read_bytes(),
            file_name=notice["attachment_name"] or "notice-attachment",
        )
    first, second = st.columns([1, 5])
    with first:
        if st.button("Remove from saved" if notice["is_saved"] else "Save notice", key="detail_save"):
            db.toggle_favourite(user["id"], notice["id"])
            st.rerun()
    with second:
        st.caption(f"Published by {notice['author']}. Original notice text is official; assistant summaries are separate.")
    return True


def _render_notice_form(user: dict, existing: dict | None = None) -> None:
    editing = existing is not None
    prefix = f"edit_notice_{existing['id']}" if editing else "new_notice"
    title = st.text_input("Notice title", value=existing["title"] if editing else "", max_chars=180, key=f"{prefix}_title")
    description = st.text_area(
        "Full notice", value=existing["description"] if editing else "", height=150, max_chars=20_000,
        key=f"{prefix}_description",
    )
    one, two = st.columns(2)
    with one:
        category = st.selectbox(
            "Category", db.CATEGORIES,
            index=db.CATEGORIES.index(existing["category"]) if editing else 0,
            key=f"{prefix}_category",
        )
        departments = st.multiselect(
            "Departments", db.DEPARTMENTS,
            default=existing["departments"].split(",") if editing else ["All"],
            help="Choose All for the entire campus, or choose specific departments.",
            key=f"{prefix}_departments",
        )
        priority = st.selectbox(
            "Priority", db.PRIORITIES,
            index=db.PRIORITIES.index(existing["priority"]) if editing else 0,
            key=f"{prefix}_priority",
        )
    with two:
        years = st.multiselect(
            "Academic years", db.ACADEMIC_YEARS,
            default=existing["years"].split(",") if editing else ["All"],
            key=f"{prefix}_years",
        )
        expiry_enabled = st.checkbox(
            "Set an expiry date",
            value=bool(existing and existing["expires_at"]),
            key=f"{prefix}_expiry_enabled",
        )
        expiry_date = st.date_input(
            "Expires on",
            value=date.fromisoformat(existing["expires_at"]) if editing and existing["expires_at"] else date.today() + timedelta(days=30),
            disabled=not expiry_enabled,
            key=f"{prefix}_expiry_date",
        )
        pinned = st.checkbox("Pin this notice", value=bool(existing and existing["pinned"]), key=f"{prefix}_pinned")
        published = st.checkbox(
            "Publish immediately",
            value=bool(existing["published"]) if editing else True,
            help="Leave unchecked to save a draft.",
            key=f"{prefix}_published",
        )
    external_link = st.text_input(
        "Optional external link", value=existing["external_link"] or "" if editing else "",
        placeholder="https://example.edu/…",
        key=f"{prefix}_link",
    )
    attachment = st.file_uploader(
        "Optional attachment (PDF, PNG, JPEG; max 5 MB)",
        type=["pdf", "png", "jpg", "jpeg"],
        disabled=editing,
        help="Attachments cannot be replaced while editing; create a new notice to add a different attachment.",
        key=f"{prefix}_attachment",
    )
    if editing and existing["attachment_name"]:
        st.caption(f"Current attachment: {existing['attachment_name']}")
    submitted = st.button(
        "Save changes" if editing else "Publish notice",
        type="primary",
        key=f"{prefix}_submit",
    )
    if not submitted:
        return
    if not title.strip() or not description.strip():
        st.error("A title and full notice description are required.")
        return
    if external_link and not external_link.lower().startswith(("https://", "http://")):
        st.error("External links must start with http:// or https://.")
        return
    attachment_name = existing["attachment_name"] if editing else None
    attachment_path = existing["attachment_path"] if editing else None
    try:
        if attachment is not None and not editing:
            attachment_name, attachment_path = _safe_attachment(attachment)
        values = {
            "title": title,
            "description": description,
            "category": category,
            "departments": departments,
            "years": years,
            "priority": priority,
            "expires_at": expiry_date.isoformat() if expiry_enabled else "",
            "pinned": pinned,
            "published": published,
            "attachment_name": attachment_name,
            "attachment_path": attachment_path,
            "external_link": external_link,
        }
        if editing:
            db.update_notice(user, existing["id"], values)
            st.success("Notice updated.")
        else:
            db.create_notice(user, values)
            st.success("Notice saved.")
        st.rerun()
    except (ValueError, PermissionError, OSError) as error:
        if attachment_path and not editing:
            _remove_attachment(attachment_path)
        st.error(str(error))


def _render_login() -> None:
    left, right = st.columns([1.05, .95], gap="large")
    with left:
        st.markdown(
            '<div class="hero"><div class="eyebrow">Your campus, in sync</div>'
            '<h1>Every Important Update.<br>Never Missed.</h1>'
            '<p>Your campus notices, events, deadlines, and announcements—all in one place.</p>'
            '<div style="margin-top:1.7rem;color:#bae6fd">✦ Smart search&nbsp;&nbsp; ✦ Priority alerts&nbsp;&nbsp; '
            '✦ Personalised notices</div></div>',
            unsafe_allow_html=True,
        )
        explore_col, start_col = st.columns(2)
        if explore_col.button("Explore Notices", use_container_width=True):
            st.session_state.auth_view = "Sign in"
            st.session_state.show_notice_preview = True
        if start_col.button("Get Started", type="primary", use_container_width=True):
            st.session_state.auth_view = "Create student account"
            st.rerun()
        st.markdown("### A calmer way to stay on top of campus life")
        st.write("Find official updates, follow the dates that matter, and keep important notices close.")
        if st.session_state.get("show_notice_preview"):
            st.info("Sign in to browse notices targeted to your department and academic year.")
        st.markdown(
            '<div class="soft-panel"><div class="section-label">Recent demo announcements</div>'
            '<p>📘 Mid-semester examination timetable</p><p>⚡ Campus technical fest: Nova</p>'
            '<p>🎓 Merit scholarship applications</p><small>Fictional sample content for local demonstration.</small></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("## Welcome to Notice Buddy")
        auth_view = st.radio(
            "Account", ["Sign in", "Create student account"],
            horizontal=True, label_visibility="collapsed", key="auth_view",
        )
        if auth_view == "Sign in":
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@college.edu")
                password = st.text_input("Password", type="password")
                login = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if login:
                user = db.authenticate(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.active_page = "Dashboard"
                    st.rerun()
                else:
                    st.error("Email or password is incorrect.")
            with st.expander("Local demo accounts"):
                st.caption("Demo-only credentials. Change or remove these accounts before any public deployment.")
                st.code(
                    "Administrator  admin@noticebuddy.local  / NoticeBuddy123!\n"
                    "Student        student@noticebuddy.local / Student123!\n"
                    "Faculty        faculty@noticebuddy.local / Faculty123!"
                )
        else:
            with st.form("register_form"):
                name = st.text_input("Full name")
                email = st.text_input("College email")
                password = st.text_input("Password (at least 8 characters)", type="password")
                department = st.selectbox("Department", db.DEPARTMENTS[:-1])
                year = st.selectbox("Academic year", db.ACADEMIC_YEARS[:-1])
                register = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if register:
                try:
                    db.register_user(name, email, password, department, year)
                    st.success("Account created. Sign in to continue.")
                except ValueError as error:
                    st.error(str(error))
    st.caption("Local demonstration app · Official campus communications should be verified with the college.")


def _render_dashboard(user: dict) -> None:
    notices = db.list_notices(user)
    events = [event for event in db.list_events(user) if event["starts_at"][:10] >= date.today().isoformat()]
    unread = sum(not notice["is_read"] for notice in notices)
    urgent = sum(notice["priority"] == "Urgent" for notice in notices)
    st.markdown(
        f'<div class="hero"><div class="eyebrow">Campus updates · {date.today().strftime("%A, %B %d")}</div>'
        f'<h1>Good to see you, {_escape(user["name"].split()[0])}.</h1>'
        '<p>Your important notices, upcoming dates, and campus activity are all in one place.</p></div>',
        unsafe_allow_html=True,
    )
    metric_cols = st.columns(4)
    with metric_cols[0]:
        _metric("Published notices", len(notices), "Visible to your account")
    with metric_cols[1]:
        _metric("Unread", unread, "Updates to catch up on")
    with metric_cols[2]:
        _metric("Urgent", urgent, "Priority announcements")
    with metric_cols[3]:
        _metric("Upcoming events", len(events), "Events and deadlines")
    st.write("")
    main, side = st.columns([1.55, 1])
    with main:
        st.markdown("### Recently published")
        for notice in notices[:4]:
            _notice_card(notice, "dashboard")
        if not notices:
            st.info("No notices match your profile yet. Try adjusting your department or year in Profile & settings.")
        if st.button("Browse all notices →", key="dashboard_browse"):
            st.session_state.active_page = "Notices"
            st.rerun()
    with side:
        st.markdown("### Coming up")
        if events:
            for event in events[:5]:
                event_date = datetime.fromisoformat(event["starts_at"])
                st.markdown(
                    f'<div class="notice-card"><span class="pill">{event["category"]}</span>'
                    f'<h3 style="margin:.5rem 0">{_escape(event["title"])}</h3>'
                    f'<div class="notice-meta">{event_date.strftime("%b %d, %Y · %I:%M %p")} · {_escape(event["venue"])}</div>'
                    f'<p>{_escape(event["description"][:120])}</p></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No upcoming events yet.")
        notifications = db.get_notifications(user["id"])
        unread_notifications = sum(notification["read_at"] is None for notification in notifications)
        st.markdown(f"#### Recent activity · {unread_notifications} unread")
        for notification in notifications[:4]:
            icon = "🔔" if notification["kind"] == "notice" else "📅"
            st.write(f"{icon} {notification['message']}")


def _render_notices(user: dict) -> None:
    if _render_notice_detail(user):
        return
    st.title("Notice board")
    st.write("Search and filter campus updates. Open a notice to read the official details.")
    with st.form("notice_filters"):
        first, second, third = st.columns([2, 1, 1])
        search = first.text_input("Search notices", placeholder="Title, topic, or keyword…")
        category = second.selectbox("Category", ["All categories", *db.CATEGORIES])
        priority = third.selectbox("Priority", ["All priorities", *db.PRIORITIES])
        fourth, fifth = st.columns(2)
        quick_view = fourth.selectbox("Quick view", ["All notices", "Unread", "Pinned", "Saved", "Urgent", "Recommended"])
        sort = fifth.selectbox("Sort by", ["Newest", "Oldest", "Priority"])
        include_expired = st.checkbox("Include expired notices")
        st.form_submit_button("Apply filters")
    notices = db.list_notices(user, search, category, priority, quick_view, sort, include_expired)
    st.caption(f"{len(notices)} notice{'s' if len(notices) != 1 else ''} found")
    if not notices:
        st.info("No notices found. Try a different search or filter.")
    for notice in notices:
        _notice_card(notice)


def _render_calendar(user: dict) -> None:
    st.title("Events & deadlines")
    st.write("Keep upcoming campus dates, examination schedules, and deadlines in view.")
    all_events = db.list_events(user)
    event_by_day: dict[str, list[dict]] = {}
    for event in all_events:
        event_by_day.setdefault(event["starts_at"][:10], []).append(event)
    selected_month = st.date_input("Choose a month", value=date.today().replace(day=1), key="calendar_month")
    month_start = selected_month.replace(day=1)
    st.subheader(month_start.strftime("%B %Y"))
    month_grid = calendar.monthcalendar(month_start.year, month_start.month)
    labels = st.columns(7)
    for column, label in zip(labels, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        column.markdown(f"**{label}**")
    for week in month_grid:
        columns = st.columns(7)
        for column, day_number in zip(columns, week):
            if not day_number:
                column.caption(" ")
                continue
            day_key = date(month_start.year, month_start.month, day_number).isoformat()
            titles = event_by_day.get(day_key, [])
            with column:
                st.markdown(f"**{day_number}**")
                if titles:
                    st.caption(f"📌 {len(titles)} update{'s' if len(titles) != 1 else ''}")
    st.markdown("### Upcoming")
    upcoming = [event for event in all_events if event["starts_at"][:10] >= date.today().isoformat()]
    upcoming.sort(key=lambda event: event["starts_at"])
    if not upcoming:
        st.info("There are no upcoming events for your profile.")
    for event in upcoming:
        event_datetime = datetime.fromisoformat(event["starts_at"])
        with st.container(border=True):
            st.markdown(f"#### {event['title']}")
            st.caption(f"{event_datetime.strftime('%A, %B %d · %I:%M %p')} · {event['venue']} · {event['category']}")
            st.write(event["description"])
            saved = bool(event["is_saved"])
            if st.button("Unsave event" if saved else "Save event", key=f"event_save_{event['id']}"):
                db.toggle_saved_event(user["id"], event["id"])
                st.rerun()


def _render_assistant() -> None:
    st.title("Notice assistant")
    st.write(
        "Extract key lines and dates from a notice. This local helper does not call an AI service; "
        "it only selects text from the original and may miss context."
    )
    st.info("Assistant output is a convenience, not an official instruction. Always verify details in the original notice.")
    source = st.radio("Input type", ["Paste notice text", "Upload a notice image"], horizontal=True)
    text = ""
    if source == "Paste notice text":
        text = st.text_area("Notice text", height=220, placeholder="Paste the original notice here…")
    else:
        image_file = st.file_uploader("Upload a notice image", type=["png", "jpg", "jpeg"], key="assistant_ocr")
        if image_file:
            try:
                image = Image.open(image_file)
                st.image(image, caption="Uploaded notice", width=480)
                if st.button("Extract text from image", type="primary"):
                    try:
                        st.session_state.ocr_result = pytesseract.image_to_string(image)
                    except (pytesseract.TesseractNotFoundError, OSError) as error:
                        st.error(f"OCR is unavailable. Install Tesseract OCR and configure its path to use image extraction. Details: {error}")
                text = st.session_state.get("ocr_result", "")
            except (UnidentifiedImageError, OSError) as error:
                st.error(f"Unable to open that image: {error}")
    if text:
        st.markdown("### Original extracted text")
        st.text_area("Original text (verify OCR carefully)", value=text, height=180, disabled=True)
        result = _insights(text)
        st.markdown("### Key points · extractive summary")
        if result["summary"]:
            for line in result["summary"]:
                st.markdown(f"- {line}")
        else:
            st.info("No text was found to summarise.")
        st.markdown("### Dates and deadlines")
        st.write(", ".join(result["dates"]) if result["dates"] else "No dates detected.")
        st.markdown("### Possible actions")
        if result["actions"]:
            for line in result["actions"]:
                st.markdown(f"- {line}")
        else:
            st.write("No action-related lines detected.")
        st.download_button("Download extracted text", data=text, file_name="notice_text.txt", mime="text/plain")


def _render_admin(user: dict) -> None:
    if not _is_publisher(user):
        st.error("Your account is not authorised to publish notices.")
        return
    st.title("Publisher workspace")
    tabs = st.tabs(["Overview", "Manage notices", "New notice", "Add event", "Faculty access"])
    stats = db.publisher_statistics(user)
    with tabs[0]:
        a, b, c, d = st.columns(4)
        with a:
            _metric("Published", stats["published"])
        with b:
            _metric("Drafts", stats["drafts"])
        with c:
            _metric("Events", stats["events"])
        with d:
            _metric("Accounts" if user["role"] == "administrator" else "Notices created",
                    stats["users"] if user["role"] == "administrator" else stats["notices_created"])
        st.markdown("### Recent publishing activity")
        for item in stats["recent"]:
            status = "Published" if item["published"] else "Draft"
            st.write(f"**{item['title']}** · {item['priority']} · {status} · {item['author']} · {item['published_at'][:10]}")
    with tabs[1]:
        st.markdown("### All notices")
        for item in stats["notices"]:
            if user["role"] != "administrator" and item["author_id"] != user["id"]:
                continue
            with st.expander(f"{'📌 ' if item['pinned'] else ''}{item['title']} · {'Published' if item['published'] else 'Draft'}"):
                existing = db.get_notice(user, item["id"])
                if existing:
                    _render_notice_form(user, existing)
                action_cols = st.columns(2)
                with action_cols[0]:
                    if st.button("Archive", key=f"archive_{item['id']}"):
                        try:
                            db.archive_notice(user, item["id"])
                            st.success("Notice archived.")
                            st.rerun()
                        except (ValueError, PermissionError) as error:
                            st.error(str(error))
                with action_cols[1]:
                    if st.button("Delete permanently", key=f"delete_{item['id']}"):
                        st.session_state[f"confirm_delete_{item['id']}"] = True
                    if st.session_state.get(f"confirm_delete_{item['id']}"):
                        st.warning("This permanently removes the notice and its read/saved history.")
                        confirm_col, cancel_col = st.columns(2)
                        if confirm_col.button("Confirm delete", key=f"confirm_delete_btn_{item['id']}"):
                            try:
                                attachment_path = db.delete_notice(user, item["id"])
                                _remove_attachment(attachment_path)
                                st.session_state.pop(f"confirm_delete_{item['id']}", None)
                                st.success("Notice deleted.")
                                st.rerun()
                            except (ValueError, PermissionError) as error:
                                st.error(str(error))
                        if cancel_col.button("Cancel", key=f"cancel_delete_{item['id']}"):
                            st.session_state.pop(f"confirm_delete_{item['id']}", None)
                            st.rerun()
    with tabs[2]:
        st.markdown("### Create a campus notice")
        _render_notice_form(user)
    with tabs[3]:
        st.markdown("### Add an event or deadline")
        with st.form("event_form"):
            event_title = st.text_input("Event title", max_chars=180)
            event_description = st.text_area("Description", max_chars=20_000)
            event_date = st.date_input("Date", value=date.today() + timedelta(days=7), min_value=date.today())
            event_time = st.time_input("Time", value=datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).time())
            venue = st.text_input("Venue")
            event_category = st.selectbox("Event category", db.CATEGORIES)
            event_departments = st.multiselect("Target departments", db.DEPARTMENTS, default=["All"])
            event_years = st.multiselect("Target academic years", db.ACADEMIC_YEARS, default=["All"])
            save_event = st.form_submit_button("Publish event", type="primary")
        if save_event:
            try:
                db.create_event(
                    user,
                    {
                        "title": event_title,
                        "description": event_description,
                        "starts_at": datetime.combine(event_date, event_time).isoformat(timespec="minutes"),
                        "venue": venue,
                        "category": event_category,
                        "departments": event_departments,
                        "years": event_years,
                    },
                )
                st.success("Event published and relevant users were notified.")
                st.rerun()
            except (ValueError, PermissionError) as error:
                st.error(str(error))
    with tabs[4]:
        if user["role"] != "administrator":
            st.info("Only an administrator can grant faculty publishing access.")
        else:
            st.markdown("### Faculty publishing permissions")
            st.caption("New faculty accounts cannot publish until an administrator authorises them.")
            for faculty in (item for item in db.list_users(user) if item["role"] == "faculty"):
                name_col, access_col = st.columns([3, 1])
                name_col.write(f"**{faculty['name']}** · {faculty['email']}")
                new_access = access_col.toggle(
                    "Can publish", value=bool(faculty["can_publish"]), key=f"faculty_access_{faculty['id']}"
                )
                if new_access != bool(faculty["can_publish"]):
                    db.authorize_faculty(user, faculty["id"], new_access)
                    st.success(f"Publishing access {'granted' if new_access else 'removed'} for {faculty['name']}.")
                    st.rerun()


def _render_profile(user: dict) -> None:
    st.title("Profile & settings")
    st.write("Personalise which campus updates are recommended for you.")
    with st.form("profile_form"):
        name_col, role_col = st.columns(2)
        name_col.text_input("Name", value=user["name"], disabled=True)
        role_col.text_input("Account role", value=user["role"].replace("_", " ").title(), disabled=True)
        department = st.selectbox(
            "Department", db.DEPARTMENTS[:-1],
            index=db.DEPARTMENTS[:-1].index(user["department"]) if user["department"] in db.DEPARTMENTS[:-1] else 0,
        )
        year = st.selectbox(
            "Academic year", db.ACADEMIC_YEARS[:-1],
            index=db.ACADEMIC_YEARS[:-1].index(user["academic_year"]) if user["academic_year"] in db.ACADEMIC_YEARS[:-1] else 0,
        )
        preferred = st.multiselect(
            "Preferred notice categories",
            db.CATEGORIES,
            default=[item for item in user["categories"].split(",") if item in db.CATEGORIES],
            help="Used by the Recommended quick filter.",
        )
        notifications_enabled = st.checkbox(
            "Enable in-app notifications", value=bool(user.get("notification_enabled", 1))
        )
        save = st.form_submit_button("Save preferences", type="primary")
    if save:
        try:
            db.update_preferences(user["id"], department, year, preferred, notifications_enabled)
            st.session_state.user = db.get_user(user["id"])
            st.success("Preferences saved.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    st.markdown("### In-app notification history")
    notifications = db.get_notifications(user["id"])
    if not notifications:
        st.info("You do not have any notifications yet.")
    for notification in notifications:
        left, right = st.columns([5, 1])
        left.write(f"{'🔵' if notification['read_at'] is None else '⚪'} {notification['message']}")
        if notification["read_at"] is None and right.button("Mark read", key=f"notification_{notification['id']}"):
            db.mark_notification_read(user["id"], notification["id"])
            st.rerun()


def main() -> None:
    if not st.session_state.get("user"):
        _render_login()
        return
    user = st.session_state.user
    shared_notice = st.query_params.get("notice")
    if shared_notice:
        try:
            st.session_state.selected_notice_id = int(shared_notice)
            st.session_state.active_page = "Notices"
        except ValueError:
            st.error("This notice link is invalid.")
            st.query_params.pop("notice", None)
    with st.sidebar:
        st.markdown("## 📢 Notice Buddy")
        st.caption(f"{user['name']} · {user['role'].title()}")
        nav_items = ["Dashboard", "Notices", "Events & calendar", "Notice assistant", "Profile & settings"]
        if _is_publisher(user):
            nav_items.insert(3, "Publisher workspace")
        active_page = st.radio(
            "Navigation", nav_items,
            index=nav_items.index(st.session_state.get("active_page", "Dashboard"))
            if st.session_state.get("active_page", "Dashboard") in nav_items else 0,
            label_visibility="collapsed",
        )
        st.session_state.active_page = active_page
        st.session_state.dark_mode = st.checkbox(
            "Dark appearance", value=bool(st.session_state.get("dark_mode", False)), key="dark_mode_toggle"
        )
        notifications = db.get_notifications(user["id"])
        unread_count = sum(notification["read_at"] is None for notification in notifications)
        with st.expander(f"🔔 Notifications · {unread_count} unread"):
            if not notifications:
                st.caption("No notifications yet.")
            for notification in notifications[:10]:
                st.write(notification["message"])
                if notification["read_at"] is None and st.button("Mark read", key=f"sidebar_notification_{notification['id']}"):
                    db.mark_notification_read(user["id"], notification["id"])
                    st.rerun()
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.markdown("---")
        st.caption("Every Important Update. Never Missed.")
    if active_page == "Dashboard":
        _render_dashboard(user)
    elif active_page == "Notices":
        _render_notices(user)
    elif active_page == "Events & calendar":
        _render_calendar(user)
    elif active_page == "Notice assistant":
        _render_assistant()
    elif active_page == "Publisher workspace":
        _render_admin(user)
    elif active_page == "Profile & settings":
        _render_profile(user)


main()

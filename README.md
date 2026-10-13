# HIIT Support — Student Support & Issue Tracking System

**Official title:** *Design and Implementation of a Student Support and Issue Tracking System for HIIT Plc.*
A LASU SIWES project built with Django, Django REST Framework, Bootstrap 5 and PostgreSQL, configured for Vercel.

> **Verification status (read this first).** The code was written and byte-compiled (`py_compile`) in an
> environment without internet access, so Django could not be installed there. That means the **migrations,
> the 35 automated tests, the system checks and the Vercel deployment have NOT been executed yet.**
> Run the commands in "Running tests" on your machine first and fix anything they report before your defense.

## 1. Problem statement
Students at HIIT Plc face academic, administrative, course-registration, laboratory, technical, payment and
certificate problems. Today these are reported informally (verbally, WhatsApp, paper), so they get lost, delayed,
or cannot be tracked by the student or by management.

## 2. Proposed solution
A web platform where students submit tickets and authorised staff assign, answer, track and resolve them, with a
full audit trail and live statistics.

## 3. Objectives
1. Let students report issues in a structured way.
2. Give every issue a unique ticket ID and a visible status.
3. Let staff assign, prioritise, respond to and resolve issues.
4. Keep a permanent history (who did what, when).
5. Give management statistics (volume, resolution rate, response time).
6. Offer a REST API on the same business logic.

## 4. Features
Student: register/login, dashboard (live counts), submit issue, My Issues (search + filters), ticket detail with
timeline and staff replies, profile/password. Staff: dashboard (6 cards, weekly volume, resolution rate, first-response
time, by-status/category bars), all/open/in-progress/resolved lists with search, filters and pagination, assign,
change priority/status, respond, students and staff lists, reports. Admin: Django Admin for users, roles, issues,
responses, activity. REST API under `/api/`. Branded 403/404/500 pages.

## 5. Technology stack
Python 3.12 · Django 5 · Django REST Framework · Django Templates · Bootstrap 5.3 + Bootstrap Icons (CDN, pinned) ·
vanilla JS · PostgreSQL (Neon) in production / SQLite locally · WhiteNoise (static files) · dj-database-url · Vercel.

## 6. Project structure
```
config/            settings.py (env-based), urls.py, wsgi.py
api/index.py       Vercel serverless entry point (exposes `app`)
vercel.json        rewrites every URL to api/index.py, bundles static + templates
support/           the single Django app
  models.py        Profile, Issue, IssueResponse, IssueActivity
  services.py      ALL business rules (assign, status workflow, responses, stats) - used by web AND API
  permissions.py   role checks, decorators, rate limiter, DRF permission classes
  views.py forms.py urls.py            website
  serializers.py api_views.py api_urls.py   REST API
  admin.py tests.py
  management/commands/seed_demo.py
templates/  static/ (css, js, img)
```

## 7. Technical architecture (for your defense)
```
Browser ──HTTPS──> Vercel Function (api/index.py → Django WSGI)
                      ├─ Templates + WhiteNoise (HTML, CSS, JS)
                      ├─ Website views ─┐
                      ├─ DRF API views ─┴─> support/services.py (business rules) ─> models
                      └─ Django ORM ──SSL──> Neon PostgreSQL (users, sessions, tickets, history)
```
* The function is **stateless**: nothing is written to disk; sessions, users and tickets live in PostgreSQL, so
  redeploys and cold starts never erase data.
* Website and API both call `services.py`, so a rule (e.g. "closed tickets are read-only") exists in one place.
* Permissions are enforced on the server in views/decorators and DRF permission classes, not by hiding buttons.

## 8. Database design
| Model | Key fields | Relationships |
|---|---|---|
| `auth.User` (built in) | username, password hash, email, names | 1–1 `Profile` |
| `Profile` | role (student/staff/admin), phone, matric_number, department, created_at | 1–1 User |
| `Issue` | ticket_id (unique), title, description, category, priority, status, location, created/updated/resolved_at | student → User (PROTECT), assigned_to → User (SET NULL) |
| `IssueResponse` | message, created_at | issue → Issue (CASCADE), staff → User (SET NULL) |
| `IssueActivity` | event_type, description, created_at | issue → Issue (CASCADE), actor → User (SET NULL) |

Indexes on `Issue.status`, `category`, `created_at`; unique constraint on `ticket_id` (format `HIT-XXXXXX`).
Status workflow: `Open → In Progress → Resolved → Closed` (Resolved may be reopened to In Progress; Closed is final;
Open may be closed directly). `resolved_at` is set on Resolved/Closed and cleared on reopen.

**Statistics definitions.** *Resolved* card = Resolved + Closed. *Resolution rate* = (Resolved + Closed) ÷ Total × 100
(shown as N/A when there are no issues). *Avg first response* = mean(first staff reply time − ticket creation time)
over tickets that have a reply (N/A when none). *This week* = tickets created since Monday 00:00 (Africa/Lagos).

## 9. Local installation
```bash
git clone <your-repo-url> hiit-support && cd hiit-support
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # Windows: copy .env.example .env
```
`.env` is **not** loaded automatically (to avoid an extra dependency). Export the variables instead:
```bash
# macOS/Linux
export DEBUG=True SECRET_KEY=dev-key
# Windows PowerShell
$env:DEBUG="True"; $env:SECRET_KEY="dev-key"
```
With `DEBUG=True` and no `DATABASE_URL`, SQLite (`db.sqlite3`) is used for local development.

### Environment variables
| Name | Purpose |
|---|---|
| `SECRET_KEY` | Required when `DEBUG` is off. Generate: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DEBUG` | `True` locally, **never** in production (default False) |
| `DATABASE_URL` | PostgreSQL URL (required in production; SSL is enforced when DEBUG is off) |
| `ALLOWED_HOSTS` | Comma-separated hosts, e.g. `your-app.vercel.app` |
| `CSRF_TRUSTED_ORIGINS` | e.g. `https://your-app.vercel.app` |
The app refuses to start in production if `SECRET_KEY`, `ALLOWED_HOSTS` or `DATABASE_URL` is missing.

## 10. Migrations, admin, demo data, server
```bash
python manage.py migrate
python manage.py createsuperuser          # becomes role "Administrator" automatically
python manage.py seed_demo --password "ChooseYourOwn!42"   # optional; local only
python manage.py runserver
```
`seed_demo` creates 3 staff (`demo_staff1..3`), 4 students (`demo_student1..4`) and 16 tickets with assignments,
replies and history. It is safe to re-run, requires you to choose the password, and refuses to run with `DEBUG` off
unless `--force` is passed. **Never use it on your public production database.**

Creating staff: sign in to `/admin/` → Users → add the user → Save → edit the user → set **Profile → Role = Staff**.
Public registration can only ever create students.

## 11. Running tests
```bash
DEBUG=True python manage.py check
DEBUG=True python manage.py makemigrations --check --dry-run   # should say "No changes detected"
DEBUG=True python manage.py test
```
If `makemigrations --check` reports changes, run `python manage.py makemigrations` and commit the result (the
initial migration was written by hand).
Tests cover registration, login/logout, issue submission, ticket-ID uniqueness, student isolation, access
restrictions, assignment, status workflow, responses, activity history, API authentication/permissions,
search/filtering and dashboard statistics.

## 12. REST API (session authentication + CSRF; JSON)
| Method & URL | Who | Description |
|---|---|---|
| `GET /api/issues/` | any user | List (students: own only). Filters `?q= &status= &category= &priority= &assigned=`; paginated (`count/next/previous/results`) |
| `POST /api/issues/` | students | Create: `title, category, priority, description, location` (owner = logged-in user) |
| `GET /api/issues/<id>/` | owner / staff | Detail |
| `PATCH /api/issues/<id>/` | staff | Any of `status, priority, assigned_to` (workflow rules enforced) |
| `DELETE /api/issues/<id>/` | admin | **Soft delete**: closes (archives) the ticket, history kept |
| `GET/POST /api/issues/<id>/responses/` | GET owner/staff, POST staff | Responses |
| `GET /api/issues/<id>/activity/` | owner / staff | Audit timeline |
| `POST /api/issues/<id>/assign/` | staff | `{"assigned_to": <user id or null>}` |
| `GET /api/me/`, `/api/stats/`, `/api/categories/` | any user | Profile, statistics, choice lists |
Errors: `{"error": {"status": 400, "message": "...", "details": {...}}}`. Throttle: 30/min anonymous, 120/min users.
Use the browser while logged in, or `curl` with a session cookie and `X-CSRFToken` header for writes.

## 13. Security notes
CSRF on all forms, hashed passwords, validators, server-side role checks, student ownership filtering (other
students' tickets return 404), no role field on registration/profile, secrets only in env vars, secure cookies +
HSTS + SSL redirect when `DEBUG` is off, branded error pages without tracebacks, DRF throttling.
**Limitation:** the login/register rate limiter uses Django's default per-instance memory cache, so on serverless
it slows guessing but is not a global limit. For stronger protection use a shared cache (e.g. Redis) or Vercel's firewall.

## 14. Deployment
See **[DEPLOYMENT.md](DEPLOYMENT.md)** (GitHub → Neon → Vercel, env vars, migrations, troubleshooting).

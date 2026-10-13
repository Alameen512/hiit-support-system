# Deploying HIIT Support to Vercel + Neon PostgreSQL

> **Status:** the configuration below is implemented but **has not been tested on a real Vercel build.**
> Vercel's Python runtime changes over time: if a step differs from what you see, trust the current
> Vercel docs (vercel.com/docs/frameworks/backend/django, vercel.com/docs/functions/runtimes/python) and tell your
> supervisor what you verified. Do the local checks in README §11 first.

## How it is wired
* `api/index.py` exposes the Django WSGI app as `app`. `vercel.json` rewrites **every** path to it, so Django
  handles `/`, `/admin/`, `/api/…` and `/static/…`.
* Static files are served by **WhiteNoise** from the `static/` folder (`WHITENOISE_USE_FINDERS=True`), so no build
  step is required. `vercel.json` `includeFiles` bundles `static/` and `templates/` into the function.
* Nothing is written to disk; sessions are stored in PostgreSQL (`SESSION_ENGINE = db`). No background workers.
* `.python-version` pins Python 3.12; dependencies come from `requirements.txt`.
* **Migrations never run on requests or automatically at build.** You run them once, deliberately (step 7).

## 1. Push to GitHub
```bash
git init && git add . && git commit -m "HIIT Support"
git branch -M main
git remote add origin https://github.com/<you>/hiit-support.git
git push -u origin main
```
Check `git status` shows no `.env` or `db.sqlite3` (both are in `.gitignore`).

## 2. Create the Neon database
1. Sign up at neon.tech → **Create project** (pick a region near your users; Lagos users → closest EU/Africa-adjacent region).
2. Open **Connect** and copy two strings: the **pooled** URL (host contains `-pooler`) and the **direct** URL.
3. Both look like `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`. Treat them like passwords.

## 3. Import into Vercel
Vercel dashboard → **Add New → Project** → import the GitHub repo. Framework preset: **Other / Django if detected**.
Leave build/output settings at defaults (no build command needed).

## 4. Environment variables (Project → Settings → Environment Variables)
| Name | Value |
|---|---|
| `SECRET_KEY` | long random string (see README) |
| `DEBUG` | `False` |
| `DATABASE_URL` | Neon **pooled** URL |
| `ALLOWED_HOSTS` | `your-project.vercel.app` (add your custom domain too, comma-separated) |
| `CSRF_TRUSTED_ORIGINS` | `https://your-project.vercel.app` |
Vercel's own `VERCEL_URL` / `VERCEL_PROJECT_PRODUCTION_URL` hosts are added automatically by `settings.py`.
Never put these in code or commit them. Redeploy after changing variables.

## 5. Deploy
Click **Deploy** (or push to `main`). Open **Deployments → your deployment → Logs / Runtime Logs** to watch it.

## 6. Static files
Nothing to do: WhiteNoise serves `/static/…` from the function. Optional fallback if a host cannot serve them:
`python manage.py collectstatic --noinput` (outputs to `staticfiles/`, git-ignored).

## 7. Run migrations (one time, and after each model change)
From your own computer, pointing at Neon using the **direct** URL:
```bash
# macOS/Linux
export DEBUG=False SECRET_KEY=anything-for-this-command ALLOWED_HOSTS=localhost DATABASE_URL="<neon direct url>"
# Windows PowerShell:  $env:DEBUG="False"; $env:SECRET_KEY="x"; $env:ALLOWED_HOSTS="localhost"; $env:DATABASE_URL="<url>"
python manage.py migrate
```
Only additive migrations should be run this way; back up (Neon branch/snapshot) before risky ones.

## 8. Create the first administrator
Same shell as step 7:
```bash
python manage.py createsuperuser
```
Sign in at `https://<your-app>/admin/`. Create staff via Users → Profile → Role = Staff.
Do **not** run `seed_demo` against production unless you accept demo accounts (it needs `--force` and a password).

## 9. Verify the deployment
1. `/` landing page renders with styling (CSS/icons loaded).
2. Register a student → dashboard → submit an issue → ticket detail with timeline.
3. Sign in as staff → assign, change status, reply.
4. `/admin/` loads with styling. `/api/issues/` returns JSON when logged in.
5. Trigger a redeploy and confirm the data is still there (it lives in Neon).

## 10. Troubleshooting
| Symptom | Likely cause / fix |
|---|---|
| Build fails installing packages | Check the build log; confirm `requirements.txt` and `.python-version` (3.12). |
| 500 on every page; log says `ImproperlyConfigured` | A required env var is missing (`SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`). |
| `DisallowedHost` / 400 | Add the domain to `ALLOWED_HOSTS` and redeploy. |
| "CSRF verification failed" on login/forms | Add `https://<domain>` to `CSRF_TRUSTED_ORIGINS`; use https; clear cookies. |
| `relation "support_issue" does not exist` | Migrations not run → step 7. |
| `connection refused` / SSL errors / timeouts | Wrong `DATABASE_URL`; ensure `sslmode=require`; use the pooled URL in Vercel; Neon may wake from idle (retry). |
| `prepared statement … already exists` | You used a pooled URL with a driver setting that conflicts; settings already disable server-side cursors—re-check the URL. |
| Unstyled pages / 404 on `/static/css/app.css` | Confirm `static/` is committed and `vercel.json` `includeFiles` is present; check logs; see §6 fallback. |
| Admin unstyled | Admin CSS comes from Django via WhiteNoise finders; redeploy and check logs. |

Logs: Vercel dashboard → project → **Logs** (runtime) and the **Deployments → Build Logs**.

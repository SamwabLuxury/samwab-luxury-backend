# Samwab API

Back end for Samwab Luxury, a vault for vintage luxury. Pieces are verified once,
stored near buyers, and can change owner without moving. This repository holds the
Django API. The front ends live in their own repository.

## Stack

| Tool | Version |
|---|---|
| Python | 3.13 |
| Django | 6.1 |
| Django REST Framework | 3.18 |
| Tests | pytest, pytest-django |
| Code quality | Ruff (lint and format), mypy |

## Run it on your machine

You need Python 3.13 and Git. On Windows, use Git Bash.

```bash
python -m venv .venv
source .venv/Scripts/activate        # macOS and Linux: source .venv/bin/activate
python -m pip install -r requirements/dev.txt
cp .env.example .env                 # then set DJANGO_SECRET_KEY to any long random text
python manage.py runserver
```

Open http://127.0.0.1:8000/api/v1/health/ and you should see `{"status": "ok"}`.

Do not run `python manage.py migrate` yet. The custom user model arrives in a later
build and must exist before the first migration.

## Checks to run before you push

```bash
python -m ruff check .          # lint
python -m ruff format .         # format
python -m mypy                  # type check
python manage.py check          # Django's own checks
python -m pytest                # tests
```

To run the lint and format checks automatically before every commit, run
`pre-commit install` once.

## Project structure

```
apps/                 our code, one folder per business area
  core/               shared building blocks used by every other app
    api/              views and URLs
    tests/            tests for this app
configurations/       project wiring only
  settings/           base.py plus one file per environment
  urls.py             mounts each app's URLs under /api/v1/
requirements/         base.txt, dev.txt, prod.txt
.github/workflows/    CI: lint, types, checks and tests on every pull request
```

Inside an app, code is split by job:

- `models.py`: data only.
- `selectors.py`: reads.
- `services.py`: writes and business rules.
- `api/`: thin views that check input, call one service and return the result.

Files are added when an app needs them, so not every app has every file.

## Apps

| App | What it owns |
|---|---|
| `core` | Shared building blocks. Today: the health endpoint. |

## API

| Method and path | Purpose | Login needed |
|---|---|---|
| `GET /api/v1/health/` | Says the API is running | No |

Every endpoint needs a logged-in user unless the table says otherwise.

## Settings and environment variables

Pick the settings file with `DJANGO_SETTINGS_MODULE`. `manage.py` uses
`configurations.settings.local`. Tests use `configurations.settings.test`.
Servers use `configurations.settings.production` (or `staging`).

| Variable | Needed in | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | everywhere | Long random text used for signing |
| `DJANGO_ALLOWED_HOSTS` | staging, production | Host names the API answers to, comma separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | staging, production | Front-end addresses allowed to send forms, comma separated |

Secrets never go into Git. `.env` is ignored, and `.env.example` lists every variable.

## Branches

- `main`: production.
- `dev`: deployed first. All work merges here.
- `feature/...`: one branch per build, merged into `dev` by pull request.

## Build status

Last build: 00, project skeleton.

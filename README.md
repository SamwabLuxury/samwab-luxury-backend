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
| API description | drf-spectacular (OpenAPI 3) |
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
    ids.py            new_uuid(): the ID every row gets
    models.py         BaseModel: id, created_at, updated_at
    money.py          Money: whole cents plus a currency
    policy.py         time limits and default rates
    exceptions.py     AppError: what services raise when a rule says no
    request_id.py     gives every request an ID
    logs.py           puts the request ID on log lines; JSON logs
    api/              views and URLs
      errors.py       the one error format
      pagination.py   the one way lists are paged
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
| `core` | Shared building blocks: IDs, `BaseModel`, `Money`, policy values, errors, paging, request IDs, the API description and the health endpoint. |

## Shared building blocks

Every app uses these, so learn them first. They live in `apps/core`.

| Use | Import | Rule |
|---|---|---|
| A new model | `from apps.core.models import BaseModel` | Every model extends `BaseModel`. It adds `id`, `created_at` and `updated_at`. |
| A new ID | `from apps.core.ids import new_uuid` | IDs are UUID version 7: they sort by creation time and cannot be guessed. |
| An amount of money | `from apps.core.money import Money` | Money is whole cents plus a currency. Never use floats or decimals. |
| A time limit or default rate | `from apps.core import policy` | Read the value from `policy`. Never type the number into your own code. |
| A business rule that says no | `from apps.core.exceptions import AppError` | Services raise `AppError` (or `NotFoundError`, `PermissionDeniedError`, `ConflictError`). They never build an HTTP response. |

```python
from apps.core.money import Money

price = Money(100_000)  # $1,000.00
commission = price.share(2_500)  # 25% -> Money(25_000)
owner_share = price - commission  # Money(75_000)
deposit, rest = price.split([1, 1])  # two parts that add up to the price
```

`Money` refuses negative amounts, floats and mixed currencies, so those mistakes
fail at once and never reach the database.

## API

| Method and path | Purpose | Login needed |
|---|---|---|
| `GET /api/v1/health/` | Says the API is running | No |
| `GET /api/v1/docs/` | A page to browse and try every endpoint | No |
| `GET /api/v1/schema/` | The OpenAPI file. Import it into Postman. Add `?format=json` for JSON | No |

Every endpoint needs a logged-in user unless the table says otherwise.

The docs and the OpenAPI file are built from the code, so they are always current.

### Errors

Every error has the same shape, with the content type `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "errors": [
    {"field": "address.city", "code": "required", "message": "This field is required."}
  ],
  "request_id": "0193a1b2c3d47e5f8a1b2c3d4e5f6a7b"
}
```

- `code` never changes for a given error, so the front end decides what to do from `code`.
- `detail` and `message` are written for people and may be reworded.
- `errors` appears only when single fields are wrong. `field` is `null` when the
  problem is with the request as a whole. Items in a list show their position: `lines.1.price`.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | One or more fields are wrong |
| 400 | `parse_error` | The body is not valid JSON |
| 400 | a rule's own code, such as `bid_too_low` | A business rule said no |
| 401 | `not_authenticated` | Not logged in |
| 403 | `permission_denied` | Logged in, but not allowed |
| 404 | `not_found` | No such address or object |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 409 | `conflict` | The request clashes with the current state |
| 415 | `unsupported_media_type` | The body is not sent as JSON |
| 429 | `throttled` | Too many requests. See the `Retry-After` header |
| 500 | `server_error` | Our fault. The cause is in the logs, never in the response |

### Lists and paging

Every list is paged the same way: 25 rows per page, newest first.

```json
{"next": "http://.../?cursor=cD0w...", "previous": null, "results": []}
```

Follow `next` until it is `null`. Ask for a different size with `?page_size=50`
(100 at most). There are no page numbers.

### Request IDs

Every response has an `X-Request-ID` header, and errors repeat it as `request_id`.
Every log line written while handling the request carries the same ID. When
something goes wrong, ask for that ID and search the logs for it. A caller may
send its own `X-Request-ID` (8 to 64 letters, digits, `.`, `_` or `-`).

Logs are plain text on your machine and one JSON object per line on servers.

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

Last build: 03, API basics (error format, paging, request IDs, API description).

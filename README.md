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
| Sign-up and login | django-allauth 65 (headless API) |
| Password hashing | Argon2 |
| Piece attribute rules | jsonschema 4.26 (JSON Schema draft 2020-12) |
| Tests | pytest, pytest-django |
| Code quality | Ruff (lint and format), mypy |

## Contents

1. [Set up your machine](#set-up-your-machine) (first time only, about 15 minutes)
2. [Run the app](#run-the-app)
3. [Try it](#try-it): the admin site, the API docs, sign-up from the command line
4. [Everyday commands](#everyday-commands)
5. [How we write code](#how-we-write-code): layers, test-driven development, test rules
6. [Checks to run before you push](#checks-to-run-before-you-push)
7. [Git and build scripts](#git-and-build-scripts)
8. [When something goes wrong](#when-something-goes-wrong)
9. Reference: [project structure](#project-structure), [apps](#apps), [shared building blocks](#shared-building-blocks), [API](#api), [settings](#settings-and-environment-variables), [build history](#build-history)

## Set up your machine

Do this once per computer. Every command below is typed in a terminal: on Windows
use **Git Bash** (it comes with Git), on macOS or Linux use the normal terminal.

### 1. Install the tools

| Tool | Why | Get it |
|---|---|---|
| Git | Get the code, save your work | https://git-scm.com/downloads (on Windows this also installs Git Bash) |
| Python 3.13 | Runs the app | https://www.python.org/downloads/ (choose 3.13.x). On Windows, tick **"Add python.exe to PATH"** in the installer |
| A code editor | Read and change the code | VS Code is what the team uses: https://code.visualstudio.com/ |

Check them. Each command should print a version:

```bash
git --version
py -3.13 --version        # Windows
python3.13 --version      # macOS and Linux
```

You do not need to install a database, Docker or Redis yet. The local database is
a single file that Django creates for you.

### 2. Get the code

```bash
cd ~/Desktop
git clone <repository address> samwab    # the address is on the repository page
cd samwab
git checkout dev                           # all work starts from dev
```

Until the GitHub repository exists, ask the lead engineer for a copy of the folder
and put it at `~/Desktop/samwab`.

### 3. Make the virtual environment

A virtual environment (`.venv`) keeps this project's packages apart from the rest
of your computer. Create it once, inside the project folder:

```bash
py -3.13 -m venv .venv            # Windows
python3.13 -m venv .venv          # macOS and Linux
```

Then **activate it**. Do this in every new terminal window, before any `python` or
`pip` command:

```bash
source .venv/Scripts/activate     # Windows (Git Bash)
source .venv/bin/activate         # macOS and Linux
```

Your prompt now starts with `(.venv)`. Check that it is the right Python:

```bash
python --version                  # must say Python 3.13.x
```

### 4. Install the packages

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

`requirements/base.txt` is what the app needs everywhere; `dev.txt` adds the test
and code-quality tools; `prod.txt` adds the web server used on servers. Versions are
pinned, so everyone gets exactly the same packages.

### 5. Create your `.env` file

The app reads its secret settings from a file called `.env`, which Git ignores.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Open `.env` in your editor and replace `change-me` with the long text the second
command printed. Nothing else is needed on your machine.

### 6. Create the database and your admin login

```bash
python manage.py migrate            # creates db.sqlite3 with every table
python manage.py createsuperuser    # asks for your email and a password
```

The superuser is your own login for the admin site. Use your real email; there is
no username.

### 7. Turn on the pre-commit checks (optional, recommended)

```bash
pre-commit install
```

From now on, every `git commit` first runs the linter and formatter on the files
you changed, so badly formatted code never reaches a commit.

## Run the app

```bash
cd ~/Desktop/samwab
source .venv/Scripts/activate       # macOS and Linux: source .venv/bin/activate
python manage.py runserver
```

Leave that terminal open; the app runs until you press `Ctrl+C`. Open a second
terminal for anything else (and activate the virtual environment there too).

| Open | What you see |
|---|---|
| http://127.0.0.1:8000/api/v1/health/ | `{"status": "ok"}`: the API is running |
| http://127.0.0.1:8000/admin/ | The admin site. Log in with your superuser email and password |
| http://127.0.0.1:8000/api/v1/docs/ | Every endpoint of our API, with a "Try it out" button |
| http://127.0.0.1:8000/_allauth/openapi.html | The sign-up and login endpoints (django-allauth) |
| http://127.0.0.1:8000/api/v1/schema/ | The OpenAPI file. Import it into Postman |

On your machine:

- `manage.py` uses `configurations.settings.local`: debug pages are on and DRF's
  browsable pages are shown.
- Emails, such as sign-up codes, are **printed in the `runserver` terminal**.
  Nothing is sent.
- The database is the file `db.sqlite3`. It is yours alone; Git ignores it.
  It moves to PostgreSQL (Neon) in build 01.

## Try it

### The catalog, in the admin site

1. Open http://127.0.0.1:8000/admin/catalog/brand/add/, type `Hermès` and save.
   The slug (`hermes`) fills itself in.
2. Add a category (`Bags`) and a design (`Kelly 28`, brand Hermès, category Bags).
3. Open http://127.0.0.1:8000/api/v1/brands/ and
   http://127.0.0.1:8000/api/v1/product-models/?brand=hermes to see them in the API.

### Sign up and log in from the command line

The web app does exactly this. Run it in a second terminal while `runserver` is
running (Git Bash on Windows includes `curl`):

```bash
API=http://127.0.0.1:8000

# 1. Get the CSRF cookie. The web app calls this once when it loads.
curl -s -c cookies.txt $API/_allauth/browser/v1/config > /dev/null
TOKEN=$(grep csrftoken cookies.txt | awk '{print $7}')

# 2. Sign up. The answer is 401 with "verify_email" pending: that is expected.
curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "correct-horse-battery-9"}' \
  $API/_allauth/browser/v1/auth/signup

# 3. Find the 6-digit code in the runserver terminal, then:
curl -s -b cookies.txt -c cookies.txt -H "X-CSRFToken: $TOKEN" \
  -H "Content-Type: application/json" -d '{"key": "123456"}' \
  $API/_allauth/browser/v1/auth/email/verify

# 4. You are logged in. See your own account:
curl -s -b cookies.txt $API/api/v1/me/
```

Delete `cookies.txt` when you are done. Section [Sign-up and login](#sign-up-and-login-django-allauth)
explains every endpoint.

## Everyday commands

Run these with the virtual environment active, from the project folder.

| Task | Command |
|---|---|
| Start the app | `python manage.py runserver` |
| Start it on another port | `python manage.py runserver 8001` |
| Run every test | `python -m pytest` |
| Run one test file | `python -m pytest apps/catalog/tests/test_api.py` |
| Run one test | `python -m pytest apps/catalog/tests/test_api.py::test_brands_are_public_and_match_the_contract` |
| Run tests whose name matches | `python -m pytest -k slug` |
| Run only the tests that failed last time | `python -m pytest --lf` |
| Stop at the first failure, show prints | `python -m pytest -x -s` |
| Tests with coverage | `python -m pytest --cov --cov-report=term-missing` |
| Make migrations after changing a model | `python manage.py makemigrations` |
| Apply migrations | `python manage.py migrate` |
| See which migrations are applied | `python manage.py showmigrations` |
| A Python shell with the app loaded | `python manage.py shell` |
| Start the local database again from empty | Stop `runserver`, delete `db.sqlite3`, then `python manage.py migrate` and `python manage.py createsuperuser` |
| Update packages after a pull | `python -m pip install -r requirements/dev.txt` |

Tests use their own settings (`configurations.settings.test`) and a fresh, empty
database every run. They never touch your `db.sqlite3`.

## How we write code

### Where code goes

Each business area is one app under `apps/`. Inside an app, code is split by job,
and each layer only calls the layers below it:

```
api/views.py      thin: check the input, call one selector or service, return the result
api/serializers.py  the shape of the JSON in and out; no business rules
services.py       every write and every business rule (raises AppError when a rule says no)
selectors.py      every read the API needs (what the public may see, in which order)
models.py         tables, database constraints and simple field checks in clean()
```

Rules:

- No business logic in views, serializers, `save()` or signals. If you are writing
  an `if` about a business rule in a view, it belongs in a service.
- Apps talk to each other only through their services and selectors.
- A rule the database can enforce (unique, check) is also a database constraint,
  so no code path can break it.
- Money is always `Money` (whole cents). Time limits and rates come from `policy`.
- Staff write through services too: the admin's `save_model` and actions call them.

### Test-driven development (TDD)

We write the test **before** the code. Every change follows the same loop:

1. **Red.** Write a test that describes one behaviour, run it, and watch it fail.
   A test you have never seen fail proves nothing.
2. **Green.** Write the simplest code that makes it pass. Run the whole suite.
3. **Refactor.** Clean up the code and the test while everything stays green.
4. Repeat for the next behaviour, then the edge cases.

A real example from the catalog:

```python
# 1. Red: apps/catalog/tests/test_api.py. Fails: there is no /api/v1/brands/ yet.
def test_brands_are_in_alphabetical_order_and_leave_out_retired_ones(client):
    for name in ("Hermès", "Chanel", "Rolex"):
        make_brand(name)
    make_brand("Ancienne Maison", is_active=False)

    rows = client.get("/api/v1/brands/").json()["results"]

    assert [row["slug"] for row in rows] == ["chanel", "hermes", "rolex"]


# 2. Green: the selector decides what the public sees, the view stays thin.
def public_brands():
    return Brand.objects.filter(is_active=True)
```

Write the test so its name reads as a sentence about the behaviour
(`test_a_slug_cannot_change_after_it_is_created`), and lay out its body in three
parts separated by blank lines: set up, act, check.

### Test rules

- Tests live next to the code: `apps/<app>/tests/test_<subject>.py`.
- Make rows with the app's helpers, such as `make_brand()` or `make_protocol()` in
  `apps/catalog/tests/helpers.py`. They fill in sensible defaults, so a test only
  names what it cares about. Add a helper when you add a model.
- Mark tests that use the database with `pytestmark = pytest.mark.django_db`.
- Outside services (Stripe, the model service, email, couriers) are replaced with
  fakes. Tests never call the internet.
- Every endpoint is tested for: success, not logged in, wrong role, someone else's
  object, invalid input, not found, and the same request twice.
- Think through the edge cases that apply: empty, missing, too long, wrong type,
  non-English text, zero, negative and very large amounts; an illegal status
  change; the same action twice; a deadline exactly on time; two requests at once;
  page boundaries; database constraints.
- Every bug gets a test that fails without the fix.
- Coverage of `apps/` is 100%. A line no test reaches is either untested behaviour
  (write the test) or dead code (delete it).

## Checks to run before you push

These are exactly what CI (`.github/workflows/ci.yml`) and every build script run.
All of them must pass.

```bash
python -m ruff check .                                       # lint
python -m ruff format --check .                              # format (run without --check to fix)
python -m mypy                                               # type check
python manage.py check                                       # Django's own checks
python manage.py makemigrations --check --dry-run            # a model change without a migration
python manage.py spectacular --validate --fail-on-warn > /dev/null   # the API description builds
python -m pytest --cov --cov-report=term-missing             # tests and coverage
```

## Git and build scripts

### Branches

- `main`: production.
- `dev`: deployed first. All work merges here.
- `feature/<short-name>`: one branch per task or build, made from `dev`.

```bash
git checkout dev
git checkout -b feature/b14-pieces       # one feature per branch
# ... write the test, write the code, run the checks ...
git add .
git commit -m "Build 14: pieces"
git checkout dev
git merge --no-ff feature/b14-pieces -m "Merge build 14: pieces"
git branch -d feature/b14-pieces
```

Once the GitHub repository exists, push the feature branch and open a pull request
into `dev` instead of merging on your machine; CI must be green before merging.

Never commit `.env`, `db.sqlite3` or `.venv`. `.gitignore` already leaves them out.

### Build scripts

The lead engineer receives each build as one script, run from Git Bash:

```bash
cd ~/Desktop/samwab && git checkout dev && git status --short    # must print nothing
bash ~/Downloads/build_<number>_<name>.sh
```

The script:

1. stops before changing anything if there are uncommitted changes, you are not
   on `dev`, the venv is missing or not Python 3.13, or a file it replaces is not
   the version it expects;
2. creates `feature/b<number>-<name>` and writes the files;
3. installs packages and runs every check above;
4. applies migrations to your local database only after everything passed;
5. stops with nothing committed, and prints the commit and merge commands.

On any failure, or `Ctrl+C`, it puts everything back as it found it: the files,
the branch and the database file. The full log is saved in `~/samwab-build-logs/`.

## When something goes wrong

| What you see | Why | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'django'` | The virtual environment is not active, or packages are not installed | `source .venv/Scripts/activate`, then `python -m pip install -r requirements/dev.txt` |
| No `(.venv)` at the start of the prompt | New terminal window | Activate it again (step 3) |
| `python --version` is not 3.13 | The venv was made with another Python | Delete `.venv`, then repeat steps 3 and 4 with `py -3.13` (Windows) or `python3.13` |
| `pip` installed packages but Django still cannot be found | `pip` belonged to another Python | Always use `python -m pip ...` with the venv active |
| `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` | No `.env` file, or no key in it | Step 5 |
| `You have unapplied migration(s)` or `no such table` | Someone added a model since your last `migrate` | `python manage.py migrate` |
| `Error: That port is already in use.` | `runserver` is already running somewhere | Stop the other one with `Ctrl+C`, or use `python manage.py runserver 8001` |
| The admin login page says the email or password is wrong | Only staff can use the admin; or a typo | `python manage.py createsuperuser` makes a new staff login |
| `403` with `"code": "csrf_failed"` | A request that changes something was sent without the `X-CSRFToken` header | Call `/_allauth/browser/v1/config` first and send the `csrftoken` cookie's value in `X-CSRFToken` |
| `400` with `too_many_login_attempts` | 5 wrong passwords for that email, or a login in the first 10 seconds after sign-up | Wait 5 minutes (or 10 seconds after sign-up) |
| Saving a piece says `attributes: ... is a required property` or similar | The attributes break the category's or design's schema | Fix the attributes as the message says, or change the schema in the catalog |
| Saving a category says `Not a valid JSON Schema` | A mistake in `attribute_schema` | Check the schema; the message says which part is wrong |
| No sign-up code arrives | Emails are not sent from your machine | Look in the `runserver` terminal |
| A build script says `You have uncommitted changes` | `git status` shows changed files | Commit them, or ask the lead before discarding anything |
| A build script says a file `is not the version from the last build` | That file was edited by hand | Send that file to the lead engineer; the next script will keep your change |
| A test fails only on your machine | Usually an old database or old packages | Re-install packages (step 4); tests never use `db.sqlite3`, so check for local changes with `git status` |

## Project structure

```
apps/                 our code, one folder per business area
  accounts/           users: the User model, its manager and its admin screens
  catalog/            brands, categories, designs, materials, capture protocols and
                      comparable sales; the catalog manager
    models/           one file per subject; import models from apps.catalog.models
  pieces/             pieces: one row per physical object, its materials and its two statuses
    state.py          the allowed status moves (custody and verification)
  core/               shared building blocks used by every other app
    ids.py            new_uuid(): the ID every row gets
    models.py         BaseModel: id, created_at, updated_at
    money.py          Money: whole cents plus a currency
    policy.py         time limits and default rates
    exceptions.py     AppError: what services raise when a rule says no
    state_machine.py  StateMachine: the allowed moves for any status
    json_schema.py    check a JSON Schema, and check data against one
    request_id.py     gives every request an ID
    logs.py           puts the request ID on log lines; JSON logs
    api/              views and URLs
      errors.py       the one error format
      pagination.py   the one way lists are paged
    tests/            tests for this app
configurations/       project wiring only
  settings/           base.py plus one file per environment
  urls.py             mounts each app's URLs under /api/v1/
templates/            email wording (allauth)
requirements/         base.txt, dev.txt, prod.txt
.github/workflows/    CI: lint, types, checks and tests on every pull request
```

A typical app (`apps/catalog/`) holds `models/` (or `models.py`), `enums.py`,
`exceptions.py`, `selectors.py`, `services.py`, `admin.py`, `api/` (views,
serializers, URLs), `migrations/` and `tests/`. What each layer does is in
[Where code goes](#where-code-goes). Files are added when an app needs them, so
not every app has every file.

Other files at the top of the repository:

| File | What it is |
|---|---|
| `manage.py` | Django's command line: `runserver`, `migrate`, `shell` and so on |
| `pyproject.toml` | Settings for Ruff, mypy, pytest and coverage |
| `.pre-commit-config.yaml` | The checks `pre-commit install` runs before each commit |
| `.env.example` | Every environment variable, with notes. Copy it to `.env` |
| `.editorconfig`, `.gitattributes` | Same indentation and line endings on every editor and computer |
| `templates/` | Our own templates; today the wording of allauth's emails |

## Apps

| App | What it owns |
|---|---|
| `accounts` | Users. People log in with their email; there is no username. |
| `catalog` | What can be sold: brands, categories, named designs (such as the Kelly 28) and materials; the capture protocols staff follow for each category or design; comparable sales for fair prices. Staff run it in the admin site; the API only reads it. |
| `pieces` | Pieces: one row per physical object Samwab holds, sells or has checked, with its materials, its custody status (where it is) and its verification status (is it authentic). Staff register pieces in the admin site. |
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
| A status that changes | `from apps.core.state_machine import StateMachine` | One table of allowed moves per status, next to its model (see `apps/pieces/state.py`). Services call `MACHINE.check(current, target)` before changing it; a refused move is 409 `illegal_transition`. |
| Rules for flexible JSON data | `from apps.core.json_schema import attribute_errors, schema_errors` | Categories and designs describe piece attributes as JSON Schema (draft 2020-12). `schema_errors` checks a schema; `attribute_errors` lists every problem in some data, with where it is. |
| A list in another order | `from apps.core.api.pagination import ordered_by` | `pagination_class = ordered_by("slug")`. The first field must be unique per row (see Lists and paging). |

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
| `GET /api/v1/me/` | The logged-in user: profile, roles and onboarding steps | Yes |
| `PATCH /api/v1/me/` | Change her names, country, locale or timezone | Yes |
| `GET /api/v1/brands/` | Active brands, A to Z | No |
| `GET /api/v1/categories/` | Active categories in menu order | No |
| `GET /api/v1/product-models/` | Active named designs. Filters: `?brand=<slug>&category=<slug>` | No |
| `GET /api/v1/docs/` | A page to browse and try every endpoint | No |
| `GET /api/v1/schema/` | The OpenAPI file. Import it into Postman. Add `?format=json` for JSON | No |

Every endpoint needs a logged-in user unless the table says otherwise.

The docs and the OpenAPI file are built from the code, so they are always current.

### Users

- Everyone is a `User` (`apps/accounts/models.py`): buyers, owners, dealers and staff.
- People log in with their email address. Emails are stored in lowercase, so
  `Ada@Example.com` and `ada@example.com` are the same account.
- One account per person. Every account can buy, so there is no buyer role.
- Other roles are Django groups with these names: `owner`, `dealer`, `intake_staff`,
  `reviewer`, `catalog_editor`, `partner`, `support`, `finance`, `admin`
  (`apps/accounts/roles.py`). `owner` is added when Stripe enables her payouts,
  `dealer` when an admin approves her application, and staff roles by an admin in
  the admin site. Sign-up never grants a role.
- `signup_intent` records which sign-up page she used (`buyer`, `owner` or `dealer`).
  It only decides which onboarding she sees.
- Always get the model with `get_user_model()` or `settings.AUTH_USER_MODEL`, and
  create users with `User.objects.create_user(email, password)`.

### Sign-up and login (django-allauth)

Sign-up, login, logout, email codes and password reset are django-allauth's
headless API under `/_allauth/browser/v1/`. These endpoints use allauth's own
response and error format, not ours. allauth describes them at
http://127.0.0.1:8000/_allauth/openapi.html.

| Method and path | Purpose |
|---|---|
| `GET /_allauth/browser/v1/config` | Call once when the web app loads. It sets the `csrftoken` cookie |
| `POST /_allauth/browser/v1/auth/signup` | `{"email", "password", "intent"}`. `intent` is `buyer` (default), `owner` or `dealer` |
| `POST /_allauth/browser/v1/auth/email/verify` | `{"key": "123456"}`: the 6-digit code from the email. Logs her in |
| `POST /_allauth/browser/v1/auth/login` | `{"email", "password"}` |
| `GET /_allauth/browser/v1/auth/session` | Is she logged in? |
| `DELETE /_allauth/browser/v1/auth/session` | Log out |
| `POST /_allauth/browser/v1/auth/password/request` | `{"email"}`: sends a 6-digit reset code |
| `POST /_allauth/browser/v1/auth/password/reset` | `{"key", "password"}`: sets the new password |

How the web app uses them:

1. Every request that changes something sends the `X-CSRFToken` header with the
   value of the `csrftoken` cookie. Without it the answer is 403 `csrf_failed`.
2. Sign-up answers 401 with the `verify_email` flow pending. The account exists, but
   she is not logged in until she enters the code from her email.
3. After login or verification, call `GET /api/v1/me/`. Its `roles` and `next_steps`
   decide which screen to open: an empty `next_steps` means nothing is waiting.
4. Signing up with an email that already has an account gives the same answer as a
   new sign-up, and the owner of that email gets an "account already exists" email.
   Nobody can use sign-up or password reset to find out who has an account.
5. After 5 wrong passwords for one email, login is refused for 5 minutes
   (`too_many_login_attempts`). A login in the first 10 seconds after sign-up is also
   refused that way, because a fresh code can only be sent once every 10 seconds.

`next_steps` values: `accept_terms`, `identity_check`, `payout_account`,
`dealer_application`, `await_dealer_decision`. Until the builds that record terms,
ID checks, payout accounts and dealer applications are done, every step of the
onboarding she chose is listed until the matching role is granted.

### Catalog

The store's menus and filters read three public lists. They need no login.

- `GET /api/v1/brands/`: `id`, `name`, `slug`, A to Z by slug.
- `GET /api/v1/categories/`: `id`, `parent_id`, `name`, `slug`, `attribute_schema`.
  Lowest `sort_order` first, then by slug. `parent_id` puts a category under
  another one, so the web app builds the menu tree itself.
- `GET /api/v1/product-models/`: `id`, `brand_id`, `category_id`, `name`, `slug`,
  `era_from`, `era_to`, by slug. `?brand=hermes&category=bags` filters by slugs.
  An unknown slug gives an empty list; a badly formed one (`?brand=Hermès!`) gives
  400 `validation_error`.

Only active rows are shown. A design is hidden when it, its brand or its category
is retired.

Staff run the catalog in the admin site (`/admin/catalog/`):

- They add, rename, reorder (the `sort_order` column in the category list) and
  retire rows. Brands, categories and designs are retired, never deleted, so the
  pieces and history that point at them stay. A material added by mistake can be
  deleted.
- A slug is filled in from the name when the row is created and never changes
  afterwards, because the web app's links use it.
- The admin checks the rules before saving: a category cannot sit under its own
  children, `attribute_schema` is a JSON object, `flaw_types` is a list of codes
  such as `["pilling", "missing_stone"]`, an HS code is 6 to 10 digits, and a
  design's years run from 1800 to next year, first year before last.
- **Capture protocols** (`/admin/catalog/captureprotocol/`) list the photos and
  readings staff take of a piece, in order: for example a macro photo of the heat
  stamp, or a scale reading. A protocol is a category's default, or belongs to one
  design. Staff add a protocol (it starts as a draft, numbered v1, v2 and so on), add
  its shots, then use the "Activate" action. Activating retires the version it
  replaces. An active protocol's shots are locked, because evidence taken under it
  must keep matching it: to change it, use "Make a new draft version", which copies
  the shots. Only drafts can be deleted. A photo uses a phone, macro lens, microscope
  or loupe; a reading uses an XRF analyser, diamond tester or scale. In code,
  `selectors.active_protocol_for(category=..., product_model=...)` gives the
  protocol that applies: the design's own if it has one, otherwise the category's.
- **Comparable sales** (`/admin/catalog/comparablesale/`) record what similar
  pieces sold for, in whole US cents (convert other currencies on the sale date).
  The design, when given, must match the brand and category. They feed the
  fair-price explainer and the low-bid check in later builds.
- `attribute_schema` on a category or design must be a valid JSON Schema
  (draft 2020-12), because every piece in it is checked against it. For example, a
  category for bags could require a width:
  `{"type": "object", "properties": {"width_cm": {"type": "number", "minimum": 1}}, "required": ["width_cm"]}`.
- A category records the staff member who last changed it (`updated_by`). Every
  change becomes an audit event in build 07, and the `catalog_editor` role gets
  its permissions there too. Until then, only superusers can use these screens.

### Pieces

A piece is one physical object. Staff register pieces in the admin site
(`/admin/pieces/piece/`); there is no public piece endpoint yet (browse and
listings add it).

- **Where it came from.** `source` is `house_stock` (Samwab owns it: the owner must
  be a house account, a user with `is_house_account` ticked) or `consigned` (an
  owner sells it through Samwab: the owner must be a person, not a house account).
  Only house stock has an `acquisition_cost_minor`.
- **What it is.** Brand, category and, when known, the design (product model).
  The design must belong to that brand and category. A blank department is taken
  from the design, and a blank HS code from the category.
- **Attributes** (measurements, metal, hardware) are JSON, checked against the
  category's schema and the design's schema. Every problem is listed with where it
  is, such as `width_cm: 0 is less than the minimum of 1`.
- **Materials** are added in the list at the bottom of the piece page. A material
  that a piece uses can no longer be deleted.
- `serial_or_date_code` is for staff only and will never be shown to the public.
- Pieces are never deleted.

Two statuses, shown in the admin but never edited there:

| Status | Values | Moves |
|---|---|---|
| `custody_status` (where it is) | `with_owner`, `in_transit`, `at_intake`, `in_vault`, `with_buyer` | `with_owner` → `in_transit` → `at_intake` → `in_vault` → `in_transit` → `with_buyer` |
| `verification_status` (is it authentic) | `unverified`, `verified`, `not_authentic` | `unverified` → `verified` or `not_authentic`, decided once |

The moves are in `apps/pieces/state.py`, and only `services.move_custody` and
`services.set_verification` change a status. They lock the row and read the status
from the database first, so two people acting at once cannot skip a step. Custody
events (build 16), the ownership ledger (build 17) and authentication checks
(build 28) will call them. Returns and moves between vaults add their moves when
their rules are settled.

### Errors

Every error has the same shape, with the content type `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "code": "validation_error",
  "detail": "One or more fields are invalid.",
  "instance": "/api/v1/me/",
  "errors": [
    {"field": "address.city", "code": "required", "message": "This field is required."}
  ],
  "request_id": "0193a1b2c3d47e5f8a1b2c3d4e5f6a7b"
}
```

- `code` never changes for a given error, so the front end decides what to do from `code`.
- `detail` and `message` are written for people and may be reworded.
- `instance` is the path of the request that failed.
- `errors` appears only when single fields are wrong. `field` is `null` when the
  problem is with the request as a whole. Items in a list show their position: `lines.1.price`.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | One or more fields are wrong |
| 400 | `parse_error` | The body is not valid JSON |
| 401 | `not_authenticated` | Not logged in |
| 403 | `permission_denied` | Logged in, but not allowed |
| 403 | `csrf_failed` | The `X-CSRFToken` header is missing or wrong |
| 404 | `not_found` | No such address or object |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 409 | `conflict` | The request clashes with the current state |
| 409 | `illegal_transition` | A status change that is not allowed from the current status |
| 415 | `unsupported_media_type` | The body is not sent as JSON |
| 422 | a rule's own code, such as `bid_too_low` | A business rule said no |
| 429 | `throttled` | Too many requests. See the `Retry-After` header |
| 500 | `server_error` | Our fault. The cause is in the logs, never in the response |

### Lists and paging

Every list is paged the same way: 25 rows per page, newest first unless the
endpoint says otherwise (the catalog lists are A to Z or in menu order).

```json
{"next": "cD0yMDI2LTEx...", "previous": null, "results": []}
```

`next` and `previous` are cursors, not links. To get the next page, send the same
request again with `?cursor=<next>`. Stop when `next` is `null`. Ask for a different
size with `?page_size=50` (100 at most), and send it again with every page.
There are no page numbers.

For developers: a list in another order uses
`pagination_class = ordered_by("slug")` (`apps/core/api/pagination.py`). The cursor
stands on the first field only, so that field must be unique per row. When the
display order is not unique, a selector adds a unique `position` value to sort on
(see `apps/catalog/selectors.py`); otherwise the previous page can skip rows.

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
| `DJANGO_FRONTEND_URL` | staging, production | The web app's address, used for links in emails. Default `http://localhost:3000` |
| `DJANGO_DEFAULT_FROM_EMAIL` | staging, production | Sender of every email, such as `Samwab <no-reply@samwab.com>` |
| `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_USER`, `DJANGO_EMAIL_PASSWORD`, `DJANGO_EMAIL_USE_TLS` | staging, production | The email provider's SMTP details. Port defaults to 587 and TLS to on |

Secrets never go into Git. `.env` is ignored, and `.env.example` lists every variable.
On your own machine, only `DJANGO_SECRET_KEY` is needed.

## Build status

The README is updated in every build.


Last build: 14, pieces (pieces, materials, custody and verification state machines).

## Build history

One line per build, newest last. Each build is one feature, merged into `dev`.

| Build | Date | What it added |
|---|---|---|
| 00 | 14 Nov 2026 | Project skeleton: settings per environment, requirements, Ruff, mypy, pytest, CI, health endpoint |
| 02 | 14 Nov 2026 | Core types: UUID version 7 IDs, `BaseModel`, `Money`, policy values |
| 03 | 14 Nov 2026 | API basics: one error format, cursor paging, request IDs, JSON logs, API docs |
| 04 | 14 Nov 2026 | Custom user: email login, lowercase emails, first migration, admin screens |
| 05 | 17 Nov 2026 | Sign-up and login with django-allauth, 6-digit email codes, password reset, `GET`/`PATCH /api/v1/me/`, role groups, `signup_intent`, Argon2, JSON CSRF errors, 422 for business rules, bare paging cursors |
| 12 | 21 Nov 2026 | Catalog A: `brands`, `categories`, `product_models`, `materials`; public lists `GET /api/v1/brands/`, `/categories/`, `/product-models/`; the catalog manager in the admin site |
| 13 | 21 Nov 2026 | Catalog B: `capture_protocols` and `capture_shots` (draft, active, retired versions), `comparable_sales`; their admin screens; `catalog.models` split into one file per subject |
| 13a | 21 Nov 2026 | Full README: setup from scratch, run, try it, everyday commands, how we write code and TDD, checks, Git and build scripts, troubleshooting |
| 14 | 21 Nov 2026 | Pieces: `pieces` and `piece_materials`; custody and verification state machines; attribute checks against JSON Schema; piece screens in the admin site; `StateMachine` and JSON Schema helpers in core |

Builds run in the order the roadmap sets, so numbers can skip: builds 12 to 14 came
before 06 to 11 to start on what buyers see. Build 01 (PostgreSQL on Neon) runs just before build 09.

"""The admin's second-step pages: type a code, or set up an authenticator app.

Plain Django views in the admin's look (they extend ``admin/base_site.html``). The
rules live in ``two_step``; these only read the form and choose the next page.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

from django import forms
from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache

from apps.users.accounts import selectors, two_step
from apps.users.accounts.models import User

WRONG_CODE = "That code is not right. Check the time on your phone and try the newest code."
TOO_MANY = "Too many wrong codes. Wait 15 minutes, then try again."

View = Callable[..., HttpResponse]


class CodeForm(forms.Form):
    code = forms.CharField(
        label="Code",
        max_length=40,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True}
        ),
    )


def staff_only(view: View) -> View:
    """Send anyone who is not a logged-in, active staff member to the admin login."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
            return redirect_to_login(request.get_full_path(), reverse("admin:login"))
        return view(request, *args, **kwargs)

    return wrapper


@never_cache
@staff_only
def verify(request: HttpRequest) -> HttpResponse:
    user = _staff_member(request)
    if not selectors.has_two_step_login(user):
        return _go(request, "two_step:setup")
    if two_step.has_passed(request):
        return HttpResponseRedirect(_next_page(request))
    form = CodeForm(request.POST or None)
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            if two_step.check_code(user, form.cleaned_data["code"]):
                two_step.mark_passed(request)
                return HttpResponseRedirect(_next_page(request))
            form.add_error("code", WRONG_CODE)
        except two_step.TooManyWrongCodesError:
            form.add_error("code", TOO_MANY)
            status = 429
    return _page(request, "admin/two_step/verify.html", "Two-step login", {"form": form}, status)


@never_cache
@staff_only
def setup(request: HttpRequest) -> HttpResponse:
    user = _staff_member(request)
    if selectors.has_two_step_login(user):
        return _go(request, "two_step:verify")
    secret = request.session.get(two_step.SESSION_SECRET)
    if request.method == "POST" and not secret:
        return _go(request, "two_step:setup")  # the set-up page was never opened
    if not secret:
        secret = request.session[two_step.SESSION_SECRET] = two_step.new_secret()
    form = CodeForm(request.POST or None)
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            codes = two_step.turn_on(user, secret, form.cleaned_data["code"])
        except two_step.TooManyWrongCodesError:
            form.add_error("code", TOO_MANY)
            status = 429
        else:
            if codes is not None:
                del request.session[two_step.SESSION_SECRET]
                two_step.mark_passed(request)
                return _page(
                    request,
                    "admin/two_step/recovery_codes.html",
                    "Save your recovery codes",
                    {"codes": codes, "next_page": _next_page(request)},
                )
            form.add_error("code", WRONG_CODE)
    link = two_step.setup_link(user, secret)
    context = {
        "form": form,
        # Safe: the SVG is drawn by the qrcode package from our own link, never from input.
        "qr_svg": mark_safe(two_step.qr_svg(link)),  # noqa: S308
        "key_groups": [secret[i : i + 4] for i in range(0, len(secret), 4)],
    }
    return _page(request, "admin/two_step/setup.html", "Set up two-step login", context, status)


def _staff_member(request: HttpRequest) -> User:
    """The logged-in person as a real row: ``request.user`` is a lazy stand-in, which
    the audit log cannot name."""
    return User.objects.get(pk=cast(UUID, request.user.pk))  # staff_only: never empty


def _next_page(request: HttpRequest) -> str:
    """Where to go after the step: the page asked for, if it is on this site."""
    wanted = request.GET.get("next", "")
    if wanted and url_has_allowed_host_and_scheme(
        wanted, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return wanted
    return reverse("admin:index")


def _go(request: HttpRequest, page: str) -> HttpResponse:
    return HttpResponseRedirect(f"{reverse(page)}?next={quote(_next_page(request), safe='/')}")


def _page(
    request: HttpRequest, template: str, title: str, context: dict[str, Any], status: int = 200
) -> HttpResponse:
    full = {**admin.site.each_context(request), "title": title, **context}
    return render(request, template, full, status=status)

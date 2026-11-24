"""The admin's gate: no admin page for a staff member until she passes the second step.

Django's admin has its own login page, which skips allauth and so skips two-step
login (allauth docs, "Admin"). allauth's own fix sends people to its login page,
which this API-only project does not serve, so the admin gets its own second step
(``two_step_views``) and this middleware sends staff there.
"""

from collections.abc import Callable
from urllib.parse import quote

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse

from apps.users.accounts import selectors, two_step


class AdminTwoStepMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        page = self._second_step_page(request)
        if page:
            next_page = quote(request.get_full_path(), safe="/")
            return HttpResponseRedirect(f"{reverse(page)}?next={next_page}")
        return self.get_response(request)

    @staticmethod
    def _second_step_page(request: HttpRequest) -> str | None:
        """The second-step page this request must go to first, or None to let it through."""
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_staff):
            return None  # the admin itself answers everyone else
        path = request.path_info
        if not path.startswith(reverse("admin:index")):
            return None  # only the admin; the API has allauth's own second step
        if path in (reverse("admin:login"), reverse("admin:logout")):
            return None
        if path.startswith(reverse("two_step:verify")):
            return None  # the second-step pages themselves
        # Checked on every admin page, so a reset (lost phone) takes effect at once.
        if not selectors.has_two_step_login(user):
            return "two_step:setup"
        if not two_step.has_passed(request):
            return "two_step:verify"
        return None

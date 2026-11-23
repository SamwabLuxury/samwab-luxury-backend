"""django-allauth's account app, renamed in the admin site.

allauth calls its section "Accounts", like ours, so the admin menu showed two
"Accounts". Its section holds sign-in email addresses, so it is named that.
"""

from allauth.account.apps import AccountConfig


# allauth ships no type information, so mypy sees its class as Any.
class EmailAddressesConfig(AccountConfig):  # type: ignore[misc]
    verbose_name = "Sign-in email addresses"

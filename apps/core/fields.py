"""Model fields shared by every app."""

from typing import Any

from django.core.exceptions import FieldError
from django.core.validators import MaxLengthValidator
from django.db import models

from apps.core import encryption


class EncryptedTextField(models.TextField):  # type: ignore[type-arg]
    """Text stored encrypted in the database and read back as plain text (decision D5).

    Name the column with ``db_column="<name>_enc"``, as in the data model. Because
    each value encrypts differently every time, the database cannot compare
    them: filtering, searching and sorting on this field are refused. Only
    ``__isnull`` works. ``max_length`` limits the plain text.
    """

    description = "Text, encrypted in the database"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.max_length is not None:
            self.validators.append(MaxLengthValidator(self.max_length))

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        return None if value is None else encryption.decrypt(value)

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        return None if value is None else encryption.encrypt(value)

    def get_lookup(self, lookup_name: str) -> Any:
        if lookup_name == "isnull":
            return super().get_lookup(lookup_name)
        raise FieldError(
            f"'{self.name}' is encrypted, so it cannot be filtered with '{lookup_name}'. "
            "Only __isnull works."
        )

    def get_transform(self, lookup_name: str) -> Any:
        raise FieldError(f"'{self.name}' is encrypted; '{lookup_name}' cannot be used on it.")

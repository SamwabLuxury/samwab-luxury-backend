from django.db import models

from apps.core.ids import new_uuid


class BaseModel(models.Model):
    """The starting point for every Samwab model.

    It gives each table the same three columns:

    - ``id``: a UUID version 7, set in Python when the object is created,
      so the ID is known before the row is saved.
    - ``created_at``: set once, when the row is first saved.
    - ``updated_at``: set again on every ``save()``.

    Careful: ``QuerySet.update()`` does not call ``save()``, so it does not
    change ``updated_at``. Set it yourself when you use ``update()``.

    This class is abstract, so it has no table of its own.
    """

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

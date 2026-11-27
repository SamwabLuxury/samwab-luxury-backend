from django.urls import path

from apps.users.legal.api.views import (
    ConsentListView,
    ConsentView,
    LegalAcceptanceView,
    LegalDocumentListView,
    LegalDocumentView,
)

app_name = "legal"

urlpatterns = [
    path("legal-documents/", LegalDocumentListView.as_view(), name="documents"),
    path("legal-documents/<str:kind>/", LegalDocumentView.as_view(), name="document"),
    path("me/legal-acceptances/", LegalAcceptanceView.as_view(), name="accept"),
    path("me/consents/", ConsentListView.as_view(), name="consents"),
    path("me/consents/<str:kind>/", ConsentView.as_view(), name="consent"),
]

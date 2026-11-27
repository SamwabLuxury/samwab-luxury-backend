"""Errors from the legal app. Every message is written for the person who sees it."""

from apps.platform.core.exceptions import AppError, ConflictError


class LegalDocumentNotCurrentError(ConflictError):
    code = "legal_document_not_current"
    message = "This version has been updated. Please read the latest one and accept that."


class SignedNameRequiredError(AppError):
    code = "signed_name_required"
    message = "Please type your full name to sign."


class OrderRequiredError(AppError):
    code = "order_required"
    message = "Please choose the order this form is for."


class OrderNotNeededError(AppError):
    code = "order_not_needed"
    message = "This text applies to your whole account, not to one order."


class PrivacyPolicyNotPublishedError(ConflictError):
    code = "privacy_policy_not_published"
    message = "We can't record this yet. Please try again later."


# ---------- staff, in the admin ----------


class LegalDocumentNotDraftError(ConflictError):
    code = "legal_document_not_draft"
    message = "This text is already published, so it can't change. Make a new draft version."


class LegalDocumentNotInForceError(ConflictError):
    code = "legal_document_not_in_force"
    message = "Only the version in force can be retired."


class DraftAlreadyExistsError(ConflictError):
    code = "legal_draft_exists"
    message = "There is already a draft of this text. Finish or delete it first."


class PlaceholderTextError(AppError):
    code = "legal_text_is_placeholder"
    message = "This text still has placeholder wording. Replace it with the real text first."

from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETION_PENDING = "DELETION_PENDING"


class ProjectStatus(StrEnum):
    DRAFT = "DRAFT"
    PAUSED_UNCONFIRMED_SCOPE = "PAUSED_UNCONFIRMED_SCOPE"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETION_PENDING = "DELETION_PENDING"


class RequestStatus(StrEnum):
    OPEN = "OPEN"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    COVERED = "COVERED"
    PROPOSAL_OPEN = "PROPOSAL_OPEN"
    WAIVED = "WAIVED"
    DECLINED = "DECLINED"
    MERGED = "MERGED"
    RESOLVED = "RESOLVED"


class ChangeOrderStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_FREELANCER_APPROVAL = "AWAITING_FREELANCER_APPROVAL"
    SEND_PENDING = "SEND_PENDING"
    AWAITING_CLIENT_APPROVAL = "AWAITING_CLIENT_APPROVAL"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    CLIENT_APPROVED = "CLIENT_APPROVED"
    REJECTED_BY_FREELANCER = "REJECTED_BY_FREELANCER"
    REJECTED_BY_CLIENT = "REJECTED_BY_CLIENT"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class PaymentStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    CREATION_PENDING = "CREATION_PENDING"
    PENDING = "PENDING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"


class JobState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    FAILED_REQUIRES_REVIEW = "FAILED_REQUIRES_REVIEW"
    CANCELLED = "CANCELLED"


class ActionState(StrEnum):
    READY = "READY"
    DISPATCHING = "DISPATCHING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCEEDED = "SUCCEEDED"
    RECEIPT_CONFIRMED = "RECEIPT_CONFIRMED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CANCELLED = "CANCELLED"


class EventType(StrEnum):
    CONNECTION_SYNC_REQUESTED = "connection.sync_requested"
    CONNECTION_HEALTH_CHANGED = "connection.health_changed"
    COMMUNICATION_CREATED = "communication.created"
    COMMUNICATION_UPDATED = "communication.updated"
    COMMUNICATION_DELETED = "communication.deleted"
    REQUEST_ASSESSMENT_REQUESTED = "request.assessment_requested"
    REQUEST_CLARIFICATION_REQUIRED = "request.clarification_required"
    SCOPE_BASELINE_CONFIRMED = "scope.baseline_confirmed"
    SCOPE_AMENDMENT_ACCEPTED = "scope.amendment_accepted"
    PROPOSAL_READY = "proposal.ready"
    PROPOSAL_FREELANCER_APPROVED = "proposal.freelancer_approved"
    PROPOSAL_FREELANCER_REJECTED = "proposal.freelancer_rejected"
    PROPOSAL_SENT = "proposal.sent"
    PROPOSAL_CLIENT_APPROVED = "proposal.client_approved"
    PROPOSAL_REVISION_REQUESTED = "proposal.revision_requested"
    PROPOSAL_CLIENT_REJECTED = "proposal.client_rejected"
    PROPOSAL_WITHDRAWN = "proposal.withdrawn"
    PAYMENT_LINK_CREATED = "payment.link_created"
    PAYMENT_OBSERVED = "payment.observed"
    PAYMENT_RECONCILED = "payment.reconciled"
    PAYMENT_REVIEW_REQUIRED = "payment.review_required"
    REMINDER_DUE = "reminder.due"
    NOTIFICATION_REQUESTED = "notification.requested"


REQUEST_TRANSITIONS = {
    (RequestStatus.OPEN, "evidence_missing"): RequestStatus.CLARIFICATION_REQUIRED,
    (RequestStatus.OPEN, "verified_covered"): RequestStatus.COVERED,
    (RequestStatus.OPEN, "proposal_assembled"): RequestStatus.PROPOSAL_OPEN,
    (RequestStatus.CLARIFICATION_REQUIRED, "human_corrected"): RequestStatus.OPEN,
    (RequestStatus.OPEN, "waived"): RequestStatus.WAIVED,
    (RequestStatus.PROPOSAL_OPEN, "waived"): RequestStatus.WAIVED,
    (RequestStatus.OPEN, "declined"): RequestStatus.DECLINED,
    (RequestStatus.PROPOSAL_OPEN, "declined"): RequestStatus.DECLINED,
    (RequestStatus.OPEN, "merged"): RequestStatus.MERGED,
    (RequestStatus.PROPOSAL_OPEN, "merged"): RequestStatus.MERGED,
    (RequestStatus.PROPOSAL_OPEN, "client_accepted"): RequestStatus.RESOLVED,
}

CHANGE_ORDER_TRANSITIONS = {
    (ChangeOrderStatus.DRAFT, "revision_ready"): ChangeOrderStatus.AWAITING_FREELANCER_APPROVAL,
    (
        ChangeOrderStatus.AWAITING_FREELANCER_APPROVAL,
        "freelancer_approved",
    ): ChangeOrderStatus.SEND_PENDING,
    (ChangeOrderStatus.SEND_PENDING, "send_confirmed"): ChangeOrderStatus.AWAITING_CLIENT_APPROVAL,
    (ChangeOrderStatus.SEND_PENDING, "client_accepted"): ChangeOrderStatus.CLIENT_APPROVED,
    (
        ChangeOrderStatus.AWAITING_CLIENT_APPROVAL,
        "client_accepted",
    ): ChangeOrderStatus.CLIENT_APPROVED,
    (
        ChangeOrderStatus.AWAITING_CLIENT_APPROVAL,
        "changes_requested",
    ): ChangeOrderStatus.REVISION_REQUESTED,
    (
        ChangeOrderStatus.REVISION_REQUESTED,
        "revision_ready",
    ): ChangeOrderStatus.AWAITING_FREELANCER_APPROVAL,
    (
        ChangeOrderStatus.AWAITING_FREELANCER_APPROVAL,
        "freelancer_rejected",
    ): ChangeOrderStatus.REJECTED_BY_FREELANCER,
    (
        ChangeOrderStatus.AWAITING_CLIENT_APPROVAL,
        "client_rejected",
    ): ChangeOrderStatus.REJECTED_BY_CLIENT,
}

PAYMENT_TRANSITIONS = {
    (PaymentStatus.NOT_REQUESTED, "client_approved"): PaymentStatus.CREATION_PENDING,
    (PaymentStatus.CREATION_PENDING, "link_verified"): PaymentStatus.PENDING,
    (PaymentStatus.PENDING, "mismatch"): PaymentStatus.REVIEW_REQUIRED,
    (PaymentStatus.CREATION_PENDING, "mismatch"): PaymentStatus.REVIEW_REQUIRED,
    (PaymentStatus.PENDING, "full_capture_verified"): PaymentStatus.PAID,
    (PaymentStatus.REVIEW_REQUIRED, "full_capture_verified"): PaymentStatus.PAID,
    (PaymentStatus.EXPIRED, "full_capture_verified"): PaymentStatus.PAID,
    (PaymentStatus.PENDING, "provider_expired"): PaymentStatus.EXPIRED,
    (PaymentStatus.PENDING, "provider_cancelled"): PaymentStatus.CANCELLED,
    (PaymentStatus.PAID, "reversal_confirmed"): PaymentStatus.REVERSED,
}

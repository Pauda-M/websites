"""Shared domain primitives and enumerations for the Program Manager.

Time, identity, and vector helpers are reused from the Cognitive Core
(`pb_api.cognitive.domain.common`) — the Program Manager never re-implements
what the core already provides. This module adds only the enumerations that
describe the Program Manager's own lifecycle, goals, authority tiers, risk, and
follow-up cadences.
"""

from __future__ import annotations

import enum

# Re-export the core primitives so PM domain modules have a single import site
# and never diverge from the core's identity/time semantics. Listed in ``__all__``
# so these re-exports are explicit under mypy strict's ``no_implicit_reexport``.
from pb_api.cognitive.domain.common import (
    AuthorityLevel,
    ensure_aware,
    new_id,
    utcnow,
)

__all__ = [
    "PM_LIFECYCLE_ORDER",
    "AuthorityLevel",
    "FollowUpCadence",
    "PMAuthorityLevel",
    "PMGoalType",
    "PMState",
    "RiskLevel",
    "ensure_aware",
    "new_id",
    "utcnow",
]


class PMState(enum.StrEnum):
    """The Program Manager's cognitive lifecycle states (Epic 008).

    The happy path advances in declaration order:
    ``IDLE → OBSERVE → UNDERSTAND → RETRIEVE_MEMORY → DETERMINE_GOAL →
    BUILD_CONTEXT → REASON → PLAN → EXECUTE → REFLECT → STORE_MEMORY →
    SCHEDULE_NEXT → IDLE``. ``AWAITING_APPROVAL`` and ``ERROR`` are off-path
    terminal states for a single run.
    """

    IDLE = "idle"
    OBSERVE = "observe"
    UNDERSTAND = "understand"
    RETRIEVE_MEMORY = "retrieve_memory"
    DETERMINE_GOAL = "determine_goal"
    BUILD_CONTEXT = "build_context"
    REASON = "reason"
    PLAN = "plan"
    EXECUTE = "execute"
    REFLECT = "reflect"
    STORE_MEMORY = "store_memory"
    SCHEDULE_NEXT = "schedule_next"
    AWAITING_APPROVAL = "awaiting_approval"
    ERROR = "error"


# The canonical happy-path order, used to validate transitions and to record the
# states a run visited.
PM_LIFECYCLE_ORDER: tuple[PMState, ...] = (
    PMState.IDLE,
    PMState.OBSERVE,
    PMState.UNDERSTAND,
    PMState.RETRIEVE_MEMORY,
    PMState.DETERMINE_GOAL,
    PMState.BUILD_CONTEXT,
    PMState.REASON,
    PMState.PLAN,
    PMState.EXECUTE,
    PMState.REFLECT,
    PMState.STORE_MEMORY,
    PMState.SCHEDULE_NEXT,
)


class PMGoalType(enum.StrEnum):
    """What the Program Manager decides to accomplish in a run."""

    REPLY_TO_CUSTOMER = "reply_to_customer"
    QUALIFY_LEAD = "qualify_lead"
    FOLLOW_UP_LEAD = "follow_up_lead"
    BOOK_MEETING = "book_meeting"
    ADVANCE_OPPORTUNITY = "advance_opportunity"
    CREATE_PROPOSAL = "create_proposal"
    UPDATE_CRM = "update_crm"
    COORDINATE_PROJECT = "coordinate_project"
    ESCALATE_ISSUE = "escalate_issue"
    REQUEST_APPROVAL = "request_approval"
    NO_ACTION = "no_action"


class PMAuthorityLevel(enum.IntEnum):
    """Program-Manager authority tiers L0-L2 (Epic 008).

    Coarser than the Cognitive Core's A0-A5 levels and mapped onto them by
    :mod:`pb_api.agents.program_manager.application.authority`. Integer-valued so
    ``>=`` comparisons express "has at least this authority".

    * ``OBSERVE_ONLY`` (L0) — read, analyse, and draft internally; every
      outward or state-changing action requires approval.
    * ``ACT_WITH_APPROVAL`` (L1) — take reversible internal actions (update CRM,
      create tasks, schedule follow-ups) autonomously; outward-facing or
      high-value actions require approval.
    * ``ACT_BOUNDED`` (L2) — send communications, book meetings, and execute
      follow-ups autonomously within configured bounds; only exceptional
      actions (large proposals/opportunities, escalations) require approval.
    """

    OBSERVE_ONLY = 0
    ACT_WITH_APPROVAL = 1
    ACT_BOUNDED = 2


class RiskLevel(enum.StrEnum):
    """The assessed risk of a plan step."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FollowUpCadence(enum.StrEnum):
    """Named follow-up cadences resolved to delays by :mod:`config`."""

    FIRST_TOUCH = "first_touch"  # 24h
    SECOND_TOUCH = "second_touch"  # 72h
    NURTURE = "nurture"  # 7d
    LONG_NURTURE = "long_nurture"  # 30d
    CUSTOM = "custom"

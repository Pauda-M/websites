"""Program Manager domain layer (pure Pydantic models and enumerations).

No I/O, no framework, no dependency on the application or infrastructure layers —
the domain is the shared vocabulary every other layer speaks.
"""

from pb_api.agents.program_manager.domain.common import (
    PM_LIFECYCLE_ORDER,
    AuthorityLevel,
    FollowUpCadence,
    PMAuthorityLevel,
    PMGoalType,
    PMState,
    RiskLevel,
    ensure_aware,
    new_id,
    utcnow,
)
from pb_api.agents.program_manager.domain.crm import (
    Contact,
    ContactRole,
    CrmTask,
    CrmTaskStatus,
    Lead,
    LeadSource,
    LeadStatus,
    Meeting,
    MeetingStatus,
    Note,
    Opportunity,
    OpportunityStage,
    Organization,
    OrganizationStatus,
    Project,
    ProjectHealth,
    ProjectStatus,
)
from pb_api.agents.program_manager.domain.events import PMEventType
from pb_api.agents.program_manager.domain.plan import (
    PMPlan,
    PMPlanStatus,
    PMPlanStep,
)
from pb_api.agents.program_manager.domain.proposal import (
    PROPOSAL_SECTION_ORDER,
    PROPOSAL_SECTION_TITLES,
    Proposal,
    ProposalSection,
    ProposalSectionKind,
    ProposalStatus,
)
from pb_api.agents.program_manager.domain.run import (
    PMRun,
    PMTask,
    PMTaskStatus,
    PMTriggerType,
)
from pb_api.agents.program_manager.domain.scheduling import (
    ScheduledAction,
    ScheduledActionKind,
    ScheduledActionStatus,
    SubjectType,
)

__all__ = [
    # common
    "PM_LIFECYCLE_ORDER",
    # proposal
    "PROPOSAL_SECTION_ORDER",
    "PROPOSAL_SECTION_TITLES",
    "AuthorityLevel",
    # crm
    "Contact",
    "ContactRole",
    "CrmTask",
    "CrmTaskStatus",
    "FollowUpCadence",
    "Lead",
    "LeadSource",
    "LeadStatus",
    "Meeting",
    "MeetingStatus",
    "Note",
    "Opportunity",
    "OpportunityStage",
    "Organization",
    "OrganizationStatus",
    "PMAuthorityLevel",
    # events
    "PMEventType",
    "PMGoalType",
    # plan
    "PMPlan",
    "PMPlanStatus",
    "PMPlanStep",
    # run
    "PMRun",
    "PMState",
    "PMTask",
    "PMTaskStatus",
    "PMTriggerType",
    "Project",
    "ProjectHealth",
    "ProjectStatus",
    "Proposal",
    "ProposalSection",
    "ProposalSectionKind",
    "ProposalStatus",
    "RiskLevel",
    # scheduling
    "ScheduledAction",
    "ScheduledActionKind",
    "ScheduledActionStatus",
    "SubjectType",
    "ensure_aware",
    "new_id",
    "utcnow",
]

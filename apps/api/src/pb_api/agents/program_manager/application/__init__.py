"""Program Manager application layer — services and the lifecycle orchestrator.

The application layer holds the Program Manager's behaviour: CRM operations,
proposal preparation, scheduling and follow-ups, deterministic planning, the
authority gate, personality/communication style, and the :class:`ProgramManager`
composition root that drives the cognitive lifecycle over the Cognitive Core.
"""

from pb_api.agents.program_manager.application.authority import AuthorityService
from pb_api.agents.program_manager.application.crm_service import CrmService
from pb_api.agents.program_manager.application.followup_engine import FollowUpEngine
from pb_api.agents.program_manager.application.program_manager import ProgramManager, RunContext
from pb_api.agents.program_manager.application.proposal_service import ProposalService
from pb_api.agents.program_manager.application.scheduler import Scheduler
from pb_api.agents.program_manager.application.task_planner import TaskPlanner

__all__ = [
    "AuthorityService",
    "CrmService",
    "FollowUpEngine",
    "ProgramManager",
    "ProposalService",
    "RunContext",
    "Scheduler",
    "TaskPlanner",
]

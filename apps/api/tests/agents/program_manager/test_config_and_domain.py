from __future__ import annotations

import uuid

import pytest

from pb_api.agents.program_manager.config import ProgramManagerSettings
from pb_api.agents.program_manager.domain.common import (
    PM_LIFECYCLE_ORDER,
    FollowUpCadence,
    PMState,
)
from pb_api.agents.program_manager.domain.crm import Opportunity, OpportunityStage
from pb_api.agents.program_manager.domain.proposal import (
    PROPOSAL_SECTION_ORDER,
    Proposal,
    ProposalSection,
)


def test_cadence_resolution_maps_named_cadences_to_seconds() -> None:
    settings = ProgramManagerSettings()
    assert settings.cadence_seconds(FollowUpCadence.FIRST_TOUCH) == 24 * 3600
    assert settings.cadence_seconds(FollowUpCadence.SECOND_TOUCH) == 72 * 3600
    assert settings.cadence_seconds(FollowUpCadence.NURTURE) == 7 * 24 * 3600
    assert settings.cadence_seconds(FollowUpCadence.LONG_NURTURE) == 30 * 24 * 3600


def test_custom_cadence_requires_positive_seconds() -> None:
    settings = ProgramManagerSettings()
    assert settings.cadence_seconds(FollowUpCadence.CUSTOM, 3600) == 3600
    with pytest.raises(ValueError, match="custom cadence"):
        settings.cadence_seconds(FollowUpCadence.CUSTOM)
    with pytest.raises(ValueError, match="custom cadence"):
        settings.cadence_seconds(FollowUpCadence.CUSTOM, 0)


def test_lifecycle_order_is_the_twelve_happy_path_states() -> None:
    assert PM_LIFECYCLE_ORDER[0] is PMState.IDLE
    assert PM_LIFECYCLE_ORDER[-1] is PMState.SCHEDULE_NEXT
    # The off-path states are not part of the happy-path order.
    assert PMState.AWAITING_APPROVAL not in PM_LIFECYCLE_ORDER
    assert PMState.ERROR not in PM_LIFECYCLE_ORDER


def test_proposal_completeness_requires_all_eleven_sections() -> None:
    assert len(PROPOSAL_SECTION_ORDER) == 11
    empty = Proposal(tenant_id=uuid.uuid4(), organization_id=uuid.uuid4(), title="P")
    assert empty.is_complete is False
    full = Proposal(
        tenant_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        title="P",
        sections=[
            ProposalSection(kind=kind, title=kind.value, content="x", order=i)
            for i, kind in enumerate(PROPOSAL_SECTION_ORDER)
        ],
    )
    assert full.is_complete is True


def test_opportunity_open_and_weighted_amount() -> None:
    opp = Opportunity(
        tenant_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Deal",
        amount=1000.0,
        probability=0.25,
        stage=OpportunityStage.PROPOSAL,
    )
    assert opp.is_open is True
    assert opp.weighted_amount == pytest.approx(250.0)
    opp.stage = OpportunityStage.CLOSED_LOST
    assert opp.is_open is False

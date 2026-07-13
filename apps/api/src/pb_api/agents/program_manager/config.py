"""Program Manager configuration.

Sourced from ``PB_PM_*`` environment variables (12-factor), independent of the
API and Cognitive Core settings so the Program Manager's authority bound,
follow-up cadences, and approval thresholds can be tuned per deployment without
touching other services.

The follow-up cadences (24h / 72h / 7d / 30d, plus a ``custom`` escape hatch) and
the approval thresholds are the levers that shape autonomous behaviour; the
personality and communication-style *content* lives in
:mod:`pb_api.agents.program_manager.application.personality` because it is
behavioural code, not deployment configuration.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from pb_api.agents.program_manager.domain.common import FollowUpCadence, PMAuthorityLevel


class ProgramManagerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PB_PM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Identity -------------------------------------------------------
    # The registered display name and role of the Program Manager AI Employee.
    agent_name: str = "Genesis Program Manager"
    agent_role: str = "program_manager"

    # --- Authority ------------------------------------------------------
    # The authority tier the Program Manager operates at by default. L1 means it
    # may take reversible internal actions autonomously but external-facing or
    # high-value actions escalate to human approval.
    default_authority: PMAuthorityLevel = PMAuthorityLevel.ACT_WITH_APPROVAL

    # --- Approval thresholds -------------------------------------------
    # A proposal whose total value is at or above this figure always requires
    # human approval before it can be marked ready/sent, regardless of tier.
    proposal_approval_value_threshold: float = 25_000.0
    # An opportunity at or above this value requires approval to advance to
    # negotiation or closed-won.
    opportunity_approval_value_threshold: float = 50_000.0

    # --- Follow-up cadences (seconds) ----------------------------------
    followup_first_touch_seconds: int = 24 * 3600  # 24h
    followup_second_touch_seconds: int = 72 * 3600  # 72h
    followup_nurture_seconds: int = 7 * 24 * 3600  # 7d
    followup_long_nurture_seconds: int = 30 * 24 * 3600  # 30d

    # --- Reasoning ------------------------------------------------------
    # Token budget for the assembled reasoning context per lifecycle run.
    reasoning_token_budget: int = 6000
    # Maximum number of steps a single plan may contain (bounds autonomy).
    max_plan_steps: int = 12

    def cadence_seconds(self, cadence: FollowUpCadence, custom_seconds: int | None = None) -> int:
        """Resolve a :class:`FollowUpCadence` to a concrete delay in seconds.

        ``custom_seconds`` is required for and only used by ``FollowUpCadence.CUSTOM``.
        """
        mapping = {
            FollowUpCadence.FIRST_TOUCH: self.followup_first_touch_seconds,
            FollowUpCadence.SECOND_TOUCH: self.followup_second_touch_seconds,
            FollowUpCadence.NURTURE: self.followup_nurture_seconds,
            FollowUpCadence.LONG_NURTURE: self.followup_long_nurture_seconds,
        }
        if cadence is FollowUpCadence.CUSTOM:
            if custom_seconds is None or custom_seconds <= 0:
                raise ValueError("custom cadence requires a positive custom_seconds")
            return custom_seconds
        return mapping[cadence]

    def cadence_delay(
        self, cadence: FollowUpCadence, custom_seconds: int | None = None
    ) -> timedelta:
        return timedelta(seconds=self.cadence_seconds(cadence, custom_seconds))


@lru_cache
def get_program_manager_settings() -> ProgramManagerSettings:
    return ProgramManagerSettings()

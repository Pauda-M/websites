"""Genesis Cognitive Core.

The cognitive operating system that autonomous AI Employees consume. It owns
working / episodic / semantic / procedural memory, memory consolidation and
ranking, the context and prompt builders, the reflection / planning / goal
engines, the agent / tool registries, the policy engine, and the event
processor.

This is a top-level bounded context (Genesis layer L3, see
`docs/genesis/003_Cognitive_Architecture.md`). It is deliberately NOT nested
under ``pb_api.core`` (which holds cross-cutting infrastructure) so the module
boundary stays clean (`docs/genesis/002_System_Architecture.md`,
`docs/genesis/adr` — the cognitive core is the platform's "core" in the product
sense, addressable at ``/api/v1/cognitive``).
"""

__all__ = ["__version__"]

__version__ = "0.1.0"

"""Genesis Program Manager — the first fully functional AI Employee.

The Program Manager owns customer communication, opportunity and project
management, proposal preparation, scheduling, follow-ups, and organizational
memory. It is not a chatbot: it is an autonomous business employee that runs a
governed cognitive lifecycle (observe → understand → retrieve → decide → plan →
execute → reflect → remember → schedule) within explicit authority limits.

It builds on and reuses the Cognitive Core (`pb_api.cognitive`) rather than
reimplementing memory, goals, planning, policy, reflection, or events. This
package is the reference implementation for every future AI Employee.

The composition root is :class:`ProgramManager` (application layer); the HTTP
surface is :data:`program_manager_router`.
"""

from pb_api.agents.program_manager.application.program_manager import ProgramManager

__all__ = ["ProgramManager"]

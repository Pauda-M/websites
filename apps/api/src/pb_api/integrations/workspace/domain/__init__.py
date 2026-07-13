"""Workspace domain layer — provider-agnostic Pydantic models and enumerations.

No I/O, no framework, no vendor SDK. Import concrete models from their submodules
(``domain.mail``, ``domain.calendar``, …); this package is the shared vocabulary
every workspace layer speaks.
"""

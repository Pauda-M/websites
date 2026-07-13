"""Errors raised by the Microsoft Graph adapter.

A single :class:`GraphError` hierarchy carries the HTTP status, the Graph error
``code`` (e.g. ``"ErrorItemNotFound"``) and a human message so callers can branch
on authentication failures without importing ``httpx``.
"""

from __future__ import annotations


class GraphError(Exception):
    """A non-successful Microsoft Graph response (after retries are exhausted).

    ``status_code`` is the HTTP status, ``code`` is Graph's ``error.code`` string
    (``None`` when the body was not a Graph error envelope), and ``message`` is the
    best available human-readable explanation.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class GraphAuthError(GraphError):
    """Authentication/authorization failure (token acquisition or a ``401``)."""

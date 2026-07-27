"""Exceptions raised by the emerald_hws library.

Callers should be able to catch failures from this library without knowing
anything about its transport. Every error raised deliberately by this package
derives from :class:`EmeraldError`.
"""


class EmeraldError(Exception):
    """Base class for all errors raised by this library."""


class EmeraldConnectionError(EmeraldError):
    """The MQTT connection is unavailable or could not be established."""


class EmeraldTimeoutError(EmeraldError, TimeoutError):
    """An MQTT operation did not complete within its deadline.

    Also derives from the builtin :class:`TimeoutError` so that callers already
    handling transport timeouts keep working unchanged.
    """

"""Exceptions raised by the emerald_hws library.

Callers should be able to catch failures from this library without knowing
anything about its transport. Every error raised deliberately by this package
derives from :class:`EmeraldError`.

The HTTP errors carry the evidence they were classified from - the HTTP status,
the response body's ``code`` and its message - so that a caller can log what
actually came back off the wire. That matters because Emerald's API has been
observed returning authentication failures during its own outages, with valid
credentials, and nobody currently has data on what such an outage looks like.
Until that data exists, ambiguous evidence is deliberately classified as
retryable: a false auth error costs a working install, a false transient error
costs a retry.
"""


class EmeraldError(Exception):
    """Base class for all errors raised by this library."""


class EmeraldConnectionError(EmeraldError):
    """A connection is unavailable or could not be established.

    Covers both the MQTT connection and transport-level failures talking to the
    HTTP API (DNS, TLS, refused connections). The originating exception is
    chained, so ``__cause__`` still holds the underlying
    :class:`requests.exceptions.RequestException` where there was one.
    """


class EmeraldTimeoutError(EmeraldError, TimeoutError):
    """An operation did not complete within its deadline.

    Also derives from the builtin :class:`TimeoutError` so that callers already
    handling transport timeouts keep working unchanged.
    """


class EmeraldApiError(EmeraldError):
    """The Emerald API answered, but not with what we asked for.

    Raised for any response the library could not use: an unexpected HTTP
    status, a body that is not JSON (an HTML error page or captive portal), a
    body whose ``code`` is not 200, or a successful-looking sign-in that came
    back without a token.

    This is the retryable classification. Anything ambiguous lands here rather
    than on :class:`EmeraldAuthError` on purpose.

    :ivar status_code: HTTP status of the response, or None if none arrived.
    :ivar api_code: the response body's ``code`` field, or None if the body was
        missing or unparseable.
    :ivar api_message: the response body's ``message`` field, if present.
    """

    def __init__(self, message, status_code=None, api_code=None, api_message=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.api_code = api_code
        self.api_message = api_message

    def _evidence(self):
        """Render the wire evidence as a short phrase, omitting absent fields."""
        parts = []
        if self.status_code is not None:
            parts.append("HTTP {}".format(self.status_code))
        if self.api_code is not None:
            parts.append("api code {}".format(self.api_code))
        detail = ", ".join(parts)
        if self.api_message:
            return (
                "{}: {}".format(detail, self.api_message)
                if detail
                else str(self.api_message)
            )
        return detail

    def __str__(self):
        # Human message first so that substring matching on it keeps working;
        # the evidence is appended for logs.
        detail = self._evidence()
        return "{} ({})".format(self.message, detail) if detail else str(self.message)

    def __repr__(self):
        return "{}({!r}, status_code={!r}, api_code={!r}, api_message={!r})".format(
            type(self).__name__,
            self.message,
            self.status_code,
            self.api_code,
            self.api_message,
        )


class EmeraldAuthError(EmeraldApiError):
    """Emerald rejected the supplied credentials at sign-in.

    Raised **only** by the sign-in endpoint. A 401 or 403 from any other
    endpoint means the *token* was refused, which is not proof that the
    password is wrong, so those stay :class:`EmeraldApiError`. A 401/403 whose
    body is not JSON is also not this error - that is an edge proxy or WAF
    talking, not the application.

    :ivar auth_evidence: which signal triggered the classification -
        ``"http_status"`` for a 401/403 response status, or ``"body_code"`` for
        an otherwise-ok response whose body ``code`` was 401/403. The HTTP
        status is the stronger signal; a caller that wants to treat a rejection
        as terminal should require it, rather than trusting the body alone.
    """

    def __init__(
        self,
        message,
        status_code=None,
        api_code=None,
        api_message=None,
        auth_evidence=None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            api_code=api_code,
            api_message=api_message,
        )
        self.auth_evidence = auth_evidence

    def __repr__(self):
        return (
            "{}({!r}, status_code={!r}, api_code={!r}, api_message={!r}, "
            "auth_evidence={!r})".format(
                type(self).__name__,
                self.message,
                self.status_code,
                self.api_code,
                self.api_message,
                self.auth_evidence,
            )
        )

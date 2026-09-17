"""Classification of HTTP failures from the Emerald API.

The governing rule: Emerald has returned authentication failures during its own
outages with valid credentials, so ambiguous evidence must never be reported as
a credential rejection. These tests pin that rule down branch by branch.
"""

import pytest
import requests

from emerald_hws import (
    EmeraldApiError,
    EmeraldAuthError,
    EmeraldConnectionError,
    EmeraldError,
    EmeraldHWS,
    EmeraldTimeoutError,
)
from emerald_hws.emeraldhws import DEFAULT_REQUEST_TIMEOUT
from .conftest import (
    MOCK_LOGIN_RESPONSE,
    MOCK_PROPERTY_RESPONSE_EMPTY,
    MOCK_PROPERTY_RESPONSE_SELF,
    make_response,
)

HTML_BODY = "<html><body><h1>502 Bad Gateway</h1></body></html>"


def client():
    return EmeraldHWS("test@example.com", "password123")


# --- success ----------------------------------------------------------------


def test_successful_login_sets_token(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    hws = client()

    assert hws.getLoginToken() is True
    assert hws.token == "mock_jwt_token_12345"


def test_body_code_200_wins_over_odd_http_status(mock_requests):
    """A good payload behind an odd status still works - the body is authoritative."""
    mock_requests.post.return_value = make_response(
        MOCK_LOGIN_RESPONSE, status_code=503
    )
    hws = client()

    assert hws.getLoginToken() is True
    assert hws.token == "mock_jwt_token_12345"


# --- genuine credential rejection -------------------------------------------


def test_http_401_is_an_auth_error(mock_requests):
    mock_requests.post.return_value = make_response(
        {"code": 401, "message": "Invalid credentials"}, status_code=401
    )
    hws = client()

    with pytest.raises(EmeraldAuthError) as exc_info:
        hws.getLoginToken()

    err = exc_info.value
    assert err.auth_evidence == "http_status"
    assert err.status_code == 401
    assert err.api_code == 401
    assert err.api_message == "Invalid credentials"
    assert isinstance(err, EmeraldApiError)
    assert isinstance(err, EmeraldError)
    assert hws.token == ""


def test_body_code_401_is_an_auth_error_but_flagged_as_weaker_evidence(mock_requests):
    mock_requests.post.return_value = make_response(
        {"code": 401, "message": "Invalid credentials"}, status_code=200
    )

    with pytest.raises(EmeraldAuthError) as exc_info:
        client().getLoginToken()

    assert exc_info.value.auth_evidence == "body_code"
    assert exc_info.value.status_code == 200


def test_evidence_is_appended_to_the_message(mock_requests):
    mock_requests.post.return_value = make_response(
        {"code": 401, "message": "Invalid credentials"}, status_code=401
    )

    with pytest.raises(EmeraldAuthError) as exc_info:
        client().getLoginToken()

    text = str(exc_info.value)
    assert text.startswith("Failed to log into Emerald API with supplied credentials")
    assert "HTTP 401" in text
    assert "api code 401" in text
    assert "Invalid credentials" in text


# --- outage shapes that must NOT be reported as auth failures ----------------


@pytest.mark.parametrize(
    "status,body",
    [
        (500, {"code": 500, "message": "Internal error"}),
        (429, {"code": 429, "message": "Too many requests"}),
        (502, {"code": 502, "message": "Bad gateway"}),
        (200, {"code": 5001, "message": "Something unrecognised"}),
        (200, {"code": 0, "message": "Unknown"}),
    ],
)
def test_server_side_failures_are_retryable_not_auth(mock_requests, status, body):
    mock_requests.post.return_value = make_response(body, status_code=status)

    with pytest.raises(EmeraldApiError) as exc_info:
        client().getLoginToken()

    assert not isinstance(exc_info.value, EmeraldAuthError)
    assert exc_info.value.status_code == status
    assert exc_info.value.api_code == body["code"]


def test_html_403_is_not_an_auth_error(mock_requests):
    """An edge proxy or WAF talking, not the application refusing a password."""
    mock_requests.post.return_value = make_response(
        None, status_code=403, text=HTML_BODY
    )

    with pytest.raises(EmeraldApiError) as exc_info:
        client().getLoginToken()

    assert not isinstance(exc_info.value, EmeraldAuthError)
    assert exc_info.value.status_code == 403


def test_html_body_becomes_an_api_error_with_the_decode_error_chained(mock_requests):
    mock_requests.post.return_value = make_response(
        None, status_code=200, text=HTML_BODY
    )

    with pytest.raises(EmeraldApiError) as exc_info:
        client().getLoginToken()

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_non_object_json_body_is_an_api_error(mock_requests):
    mock_requests.post.return_value = make_response(["not", "an", "object"])

    with pytest.raises(EmeraldApiError):
        client().getLoginToken()


def test_code_200_without_a_token_is_an_api_error(mock_requests):
    """Used to set token to None and return True, failing later as "Bearer None"."""
    mock_requests.post.return_value = make_response(
        {"code": 200, "message": "Login successful"}
    )
    hws = client()

    with pytest.raises(EmeraldApiError) as exc_info:
        hws.getLoginToken()

    assert not isinstance(exc_info.value, EmeraldAuthError)
    assert exc_info.value.api_code == 200
    assert hws.token == ""


# --- transport --------------------------------------------------------------


def test_connection_error_is_wrapped_and_chained(mock_requests):
    original = requests.exceptions.ConnectionError("name resolution failed")
    mock_requests.post.side_effect = original

    with pytest.raises(EmeraldConnectionError) as exc_info:
        client().getLoginToken()

    assert exc_info.value.__cause__ is original
    assert isinstance(exc_info.value, EmeraldError)


def test_timeout_is_wrapped_and_stays_a_builtin_timeout_error(mock_requests):
    """The HA integration branches on builtin TimeoutError - keep that working."""
    original = requests.exceptions.Timeout("timed out")
    mock_requests.post.side_effect = original

    with pytest.raises(EmeraldTimeoutError) as exc_info:
        client().getLoginToken()

    assert isinstance(exc_info.value, TimeoutError)
    assert isinstance(exc_info.value, EmeraldError)
    assert exc_info.value.__cause__ is original


def test_timeout_is_checked_before_the_broader_request_exception(mock_requests):
    """Timeout subclasses RequestException, so order of the handlers matters."""
    mock_requests.post.side_effect = requests.exceptions.Timeout("timed out")

    with pytest.raises(EmeraldTimeoutError):
        client().getLoginToken()


# --- timeout plumbing -------------------------------------------------------


def test_default_timeout_is_passed_on_every_call(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    mock_requests.get.return_value = make_response(MOCK_PROPERTY_RESPONSE_SELF)
    hws = client()

    hws.getLoginToken()
    hws.getAllHWS()

    assert mock_requests.post.call_args.kwargs["timeout"] == DEFAULT_REQUEST_TIMEOUT
    assert mock_requests.get.call_args.kwargs["timeout"] == DEFAULT_REQUEST_TIMEOUT


def test_constructor_can_override_the_timeout(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    hws = EmeraldHWS("test@example.com", "password123", request_timeout_seconds=5)

    hws.getLoginToken()

    assert mock_requests.post.call_args.kwargs["timeout"] == 5


def test_url_stays_positional(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)

    client().getLoginToken()

    assert "sign-in" in mock_requests.post.call_args[0][0]


# --- getAllHWS: a refused token is not a refused password -------------------


@pytest.mark.parametrize("status", [401, 403])
def test_property_list_rejection_is_never_an_auth_error(mock_requests, status):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    mock_requests.get.return_value = make_response(
        {"code": status, "message": "Unauthorized"}, status_code=status
    )
    hws = client()

    with pytest.raises(EmeraldApiError) as exc_info:
        hws.getAllHWS()

    assert not isinstance(exc_info.value, EmeraldAuthError)
    assert exc_info.value.status_code == status


def test_property_list_server_error_is_retryable(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    mock_requests.get.return_value = make_response(
        {"code": 500, "message": "Internal error"}, status_code=500
    )
    hws = client()

    with pytest.raises(EmeraldApiError) as exc_info:
        hws.getAllHWS()

    assert "Unable to fetch properties" in str(exc_info.value)


def test_empty_property_list_is_an_api_error(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    mock_requests.get.return_value = make_response(MOCK_PROPERTY_RESPONSE_EMPTY)
    hws = client()

    with pytest.raises(EmeraldApiError) as exc_info:
        hws.getAllHWS()

    assert "No heat pumps found" in str(exc_info.value)
    assert exc_info.value.api_code == 200


def test_getallhws_does_not_leak_the_token_onto_the_class_headers(mock_requests):
    mock_requests.post.return_value = make_response(MOCK_LOGIN_RESPONSE)
    mock_requests.get.return_value = make_response(MOCK_PROPERTY_RESPONSE_SELF)

    client().getAllHWS()

    assert "authorization" not in EmeraldHWS.COMMON_HEADERS


# --- _wait_for_properties ---------------------------------------------------


def test_wait_for_properties_times_out_with_a_typed_error():
    hws = client()

    with pytest.raises(EmeraldTimeoutError) as exc_info:
        hws._wait_for_properties(timeout=0.2)

    assert "Timeout waiting for properties" in str(exc_info.value)
    assert isinstance(exc_info.value, TimeoutError)


# --- rendering --------------------------------------------------------------


def test_message_alone_renders_without_an_empty_bracket():
    assert str(EmeraldApiError("Unable to fetch properties")) == (
        "Unable to fetch properties"
    )


def test_api_message_alone_still_renders():
    assert str(EmeraldApiError("boom", api_message="upstream unavailable")) == (
        "boom (upstream unavailable)"
    )


def test_repr_carries_the_full_evidence():
    err = EmeraldApiError("boom", status_code=500, api_code=500, api_message="nope")
    text = repr(err)

    assert text.startswith("EmeraldApiError(")
    assert "status_code=500" in text
    assert "api_message='nope'" in text


def test_auth_repr_includes_which_evidence_fired():
    err = EmeraldAuthError(
        "boom", status_code=401, api_code=401, auth_evidence="http_status"
    )

    assert "auth_evidence='http_status'" in repr(err)

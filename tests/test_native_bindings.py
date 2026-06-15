"""Regression test for awscrt Python-wrapper vs native _awscrt.so drift.

Background: a fresh HA install once failed at connect with
    "function takes exactly 43 arguments (45 given)"
because an in-place HAOS upgrade left a stale compiled _awscrt*.so (old native,
43 args) under a newer pure-Python awscrt wrapper (45 args). The version graph
stays consistent (awsiotsdk pins awscrt exactly), so the skew is purely between
the .py wrapper and the .so on disk.

Building (not starting) an mqtt5 client invokes the native
_awscrt.mqtt5_client_new binding at construction time, so it detects that skew
without any network or credentials.
"""

import pytest
from awscrt import auth
from awsiot import mqtt5_client_builder


def test_awscrt_wrapper_native_arity_in_sync():
    """Build an mqtt5 client offline to cross the awscrt native binding.

    websockets_with_default_aws_signing constructs awscrt.mqtt5.Client at build
    time, whose __init__ calls the native _awscrt.mqtt5_client_new. No .start()
    is called, so no socket is opened. If the installed awscrt .py wrapper and
    compiled _awscrt extension disagree on arg count, construction raises a
    native TypeError -- exactly the failure seen in the field.
    """
    creds = auth.AwsCredentialsProvider.new_static(
        access_key_id="AKIDEXAMPLE",
        secret_access_key="secret",
    )
    try:
        client = mqtt5_client_builder.websockets_with_default_aws_signing(
            endpoint="example-ats.iot.ap-southeast-2.amazonaws.com",
            region="ap-southeast-2",
            credentials_provider=creds,
        )  # builds Client -> _awscrt.mqtt5_client_new; no .start(), no network
    except TypeError as e:
        pytest.fail(
            "awscrt Python wrapper and native _awscrt extension are out of sync "
            f"({e!r}). The installed awscrt .py and compiled .so disagree on "
            "arg count -- typically a stale _awscrt*.so left by an in-place "
            "upgrade. Fix: pip install --force-reinstall --no-cache-dir awscrt"
        )
    assert client is not None

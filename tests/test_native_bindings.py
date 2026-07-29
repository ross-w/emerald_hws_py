"""Regression tests for awscrt version drift.

This module docstring is the canonical explanation of the problem; the code that
guards against it (`connectMQTT`) and the tests below refer here rather than
repeating it.

awscrt is a compiled extension whose Python files and native library have to
match, and it moves whenever awsiotsdk does. Two field failures came from halves
of different versions meeting inside one process:

  - `function takes exactly 43 arguments (45 given)` -- a stale compiled
    _awscrt*.so (43 args) under a newer pure-Python wrapper (45 args), left by an
    in-place HAOS upgrade. The two arguments accounting for the difference are
    the metrics pair awscrt 0.32.2 added to mqtt5_client_new.
  - `'ClientTlsContext' object has no attribute '_certificate_source'` -- a slot
    only awscrt >=0.35.0's awscrt.io declares, but which >=0.35.0's usage-metrics
    code reads unconditionally. Home Assistant loads awscrt during startup
    (`cloud` -> hass_nabucasa -> botocore, whose compat module imports it) and
    then upgrades it on disk while installing this library, so modules imported
    afterwards can meet the old cached class. The stale modules stay in
    sys.modules for the lifetime of the process, so only a restart clears it.

connectMQTT passes `enable_metrics_collection=False`, which skips the metrics
code path entirely and pins the two native metrics arguments to (False, None) --
values every awscrt release accepts. That makes the second failure unreachable.
The first is a genuine wrapper/extension arity mismatch that no Python-level flag
can bridge, since those arguments are passed positionally either way.

Building (not starting) an mqtt5 client invokes the native
_awscrt.mqtt5_client_new binding at construction time, so these tests cross it
without any network or credentials.
"""

import pytest
from awscrt import auth
from awsiot import mqtt5_client_builder

# RFC 2606 reserves .invalid, so this name can never resolve. No .start() is
# called either, so nothing here opens a socket regardless -- but a
# guaranteed-dead endpoint removes any doubt about external dependencies.
FAKE_ENDPOINT = "mqtt.example.invalid"
FAKE_REGION = "ap-southeast-2"


def _fake_credentials():
    """Throwaway static credentials, never used to sign a real request."""
    return auth.AwsCredentialsProvider.new_static(
        access_key_id="AKIDEXAMPLE",
        secret_access_key="secret",
    )


def test_awscrt_wrapper_native_arity_in_sync():
    """Build an mqtt5 client offline to cross the awscrt native binding.

    If the installed awscrt .py wrapper and compiled _awscrt extension disagree
    on argument count, construction raises a native TypeError -- the first
    failure described in the module docstring.
    """
    try:
        client = mqtt5_client_builder.websockets_with_default_aws_signing(
            endpoint=FAKE_ENDPOINT,
            region=FAKE_REGION,
            credentials_provider=_fake_credentials(),
        )  # builds Client -> _awscrt.mqtt5_client_new; no .start(), no network
    except TypeError as e:
        pytest.fail(
            "awscrt Python wrapper and native _awscrt extension are out of sync "
            f"({e!r}). The installed awscrt .py and compiled .so disagree on "
            "arg count -- typically a stale _awscrt*.so left by an in-place "
            "upgrade. Fix: pip install --force-reinstall --no-cache-dir awscrt"
        )
    assert client is not None


def test_metrics_disabled_build_crosses_native_binding():
    """Build the way connectMQTT does, with metrics collection off.

    This is the production keyword combination, so it is the one worth exercising
    against the real awscrt. See the module docstring for why metrics are off.
    """
    client = mqtt5_client_builder.websockets_with_default_aws_signing(
        endpoint=FAKE_ENDPOINT,
        region=FAKE_REGION,
        credentials_provider=_fake_credentials(),
        enable_metrics_collection=False,
    )  # builds Client -> _awscrt.mqtt5_client_new; no .start(), no network

    assert client is not None

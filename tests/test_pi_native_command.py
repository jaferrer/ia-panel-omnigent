import omnigent.pi_native as pi_native


def test_default_command_is_ompr() -> None:
    assert pi_native._configured_pi_command({}) == "ompr"


def test_env_override_wins() -> None:
    env = {"OMNIGENT_PI_PATH": "/custom/ompr"}
    assert pi_native._configured_pi_command(env) == "/custom/ompr"


def test_approve_flag_never_for_ompr_wrapper() -> None:
    assert pi_native.pi_supports_approve("/Users/x/.local/bin/ompr") is False

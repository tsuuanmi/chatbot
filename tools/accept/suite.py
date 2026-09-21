"""Acceptance suite orchestration."""

from __future__ import annotations

from .api import (
    api_contract_suite,
    auth_check,
    compile_tests,
    config_check,
    gateway_suite,
    internal_security_suite,
    policy_routing_suite,
    policy_tests,
    public_api_suite,
    runtime_python_compile,
    stream_suite,
    unit_tests,
)

from .config import (
    GATEWAY_URL,
    INTERNAL_URL,
)

from .gpu import (
    gpu_runtime_check,
)

from .media import (
    media_full_suite,
    media_quick_suite,
)

from .history import (
    context_suite,
    history_concurrency_suite,
    history_suite,
    stream_history_suite,
)

from .recovery import (
    recovery_suite,
)

from .security import (
    secret_audit,
    secret_group_check,
)


def verify() -> None:
    config_check()
    auth_check()

    unit_tests()
    compile_tests()
    policy_tests()

    policy_routing_suite()
    api_contract_suite()
    internal_security_suite()

    stream_suite(
        INTERNAL_URL,
        label="internal",
    )

    gateway_suite()
    public_api_suite()
    media_quick_suite()
    runtime_python_compile()

    print()
    print("VERIFY PASS")



def recovery() -> None:
    config_check()
    auth_check()

    recovery_suite()

def full(
    *,
    gpu: bool,
) -> None:
    verify()

    history_suite()
    context_suite()
    history_concurrency_suite()
    stream_history_suite()

    stream_suite(
        GATEWAY_URL,
        label="gateway",
    )

    media_full_suite()

    secret_audit()
    secret_group_check()

    if gpu:
        gpu_runtime_check()

    print()
    print("FULL ACCEPTANCE PASS")

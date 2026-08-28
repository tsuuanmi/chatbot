"""Tests for deterministic offline LAN address selection."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_detector() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts/offline/detect_network.py"
    spec = importlib.util.spec_from_file_location("offline_detect_network", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _interface(
    name: str,
    address: str,
    prefix_length: int,
    *,
    active: bool = True,
    carrier: bool = True,
) -> dict[str, object]:
    flags = ["UP", "LOWER_UP"] if active and carrier else ["UP"] if active else []
    return {
        "ifname": name,
        "flags": flags,
        "operstate": "UP" if active and carrier else "DOWN",
        "addr_info": [
            {
                "family": "inet",
                "local": address,
                "prefixlen": prefix_length,
                "scope": "global",
            }
        ],
    }


def test_selects_default_route_physical_interface() -> None:
    detector = _load_detector()
    routes = [{"dev": "eno1", "prefsrc": "192.168.1.208"}]
    addresses = [
        _interface("tailscale0", "100.109.66.7", 32),
        _interface("docker0", "172.17.0.1", 16),
        _interface("eno1", "192.168.1.208", 24),
    ]

    assert detector.select_network(routes, addresses) == (
        "192.168.1.208",
        "192.168.1.0/24",
        "eno1",
    )


def test_fallback_ignores_virtual_and_inactive_interfaces() -> None:
    detector = _load_detector()
    addresses = [
        _interface("eno2", "10.10.0.20", 24, active=False),
        _interface("eno3", "10.20.0.20", 24, carrier=False),
        _interface("br-123", "172.18.0.1", 16),
        # The deployed isolated LAN is globally numbered, so direct link state and
        # the selected interface prefix define trust rather than RFC1918 status.
        _interface("enp3s0", "172.119.37.115", 24),
    ]

    assert detector.select_network([], addresses) == (
        "172.119.37.115",
        "172.119.37.0/24",
        "enp3s0",
    )


def test_explicit_address_and_cidr_are_validated() -> None:
    detector = _load_detector()
    addresses = [_interface("eno1", "192.168.50.10", 24)]

    assert detector.select_network(
        [], addresses, "192.168.50.10", "192.168.50.0/25"
    ) == ("192.168.50.10", "192.168.50.0/25", "eno1")

    with pytest.raises(ValueError, match="outside LAN CIDR"):
        detector.select_network([], addresses, "192.168.50.10", "192.168.51.0/24")


def test_rejects_unassigned_inactive_and_overly_broad_networks() -> None:
    detector = _load_detector()
    addresses = [
        _interface("eno1", "192.168.1.20", 24),
        _interface("eno2", "10.0.0.20", 24, active=False),
    ]

    with pytest.raises(ValueError, match="not assigned to an active interface"):
        detector.select_network([], addresses, "10.0.0.20")
    with pytest.raises(ValueError, match="not assigned to an active interface"):
        detector.select_network([], addresses, "192.168.1.30")
    with pytest.raises(ValueError, match="too broad"):
        detector.select_network([], addresses, "192.168.1.20", "0.0.0.0/0")

#!/usr/bin/env python3
"""Detect and validate the offline server's primary IPv4 LAN network."""

from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
from dataclasses import dataclass
from typing import Any


_VIRTUAL_INTERFACE_PREFIXES = (
    "br-",
    "docker",
    "lo",
    "tailscale",
    "tun",
    "veth",
    "virbr",
    "wg",
)


@dataclass(frozen=True)
class AddressRecord:
    """One globally scoped IPv4 address assigned to a host interface."""

    interface: str
    address: ipaddress.IPv4Address
    prefix_length: int
    active: bool

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(
            f"{self.address}/{self.prefix_length}", strict=False
        )


def _parse_ipv4_address(raw_address: str) -> ipaddress.IPv4Address:
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError:
        raise ValueError(f"invalid IPv4 server address: {raw_address}") from None
    if not isinstance(address, ipaddress.IPv4Address):
        raise ValueError(f"only IPv4 server addresses are supported: {raw_address}")
    if address.is_unspecified or address.is_loopback or address.is_multicast:
        raise ValueError(f"server address is not a usable LAN address: {raw_address}")
    return address


def _parse_ipv4_network(raw_network: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(raw_network, strict=False)
    except ValueError:
        raise ValueError(f"invalid IPv4 LAN CIDR: {raw_network}") from None
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError(f"only IPv4 LAN CIDRs are supported: {raw_network}")
    if network.prefixlen < 8:
        raise ValueError(f"LAN CIDR is too broad for automatic trust: {network}")
    return network


def parse_address_records(payload: list[dict[str, Any]]) -> list[AddressRecord]:
    """Extract globally scoped IPv4 records from ``ip -j address`` output."""
    records: list[AddressRecord] = []
    for interface_payload in payload:
        interface = interface_payload.get("ifname")
        if not isinstance(interface, str) or not interface:
            continue
        flags = interface_payload.get("flags", [])
        operational_state = interface_payload.get("operstate")
        active = (
            isinstance(flags, list)
            and "UP" in flags
            and "LOWER_UP" in flags
            and operational_state in {"UP", "UNKNOWN"}
        )
        address_info = interface_payload.get("addr_info", [])
        if not isinstance(address_info, list):
            continue
        for item in address_info:
            if not isinstance(item, dict):
                continue
            if item.get("family") != "inet" or item.get("scope") != "global":
                continue
            raw_address = item.get("local")
            prefix_length = item.get("prefixlen")
            if not isinstance(raw_address, str) or not isinstance(prefix_length, int):
                continue
            try:
                address = ipaddress.IPv4Address(raw_address)
                ipaddress.IPv4Network(f"{address}/{prefix_length}", strict=False)
            except ValueError:
                continue
            records.append(AddressRecord(interface, address, prefix_length, active))
    return records


def _is_physical_candidate(record: AddressRecord) -> bool:
    return record.active and not record.interface.startswith(
        _VIRTUAL_INTERFACE_PREFIXES
    )


def select_network(
    routes: list[dict[str, Any]],
    addresses: list[dict[str, Any]],
    requested_address: str = "",
    requested_cidr: str = "",
) -> tuple[str, str, str]:
    """Select an assigned IPv4 address, its LAN CIDR, and interface name."""
    records = parse_address_records(addresses)
    if not records:
        raise ValueError("no globally scoped IPv4 address is assigned to this computer")

    selected: AddressRecord | None = None
    if requested_address:
        address = _parse_ipv4_address(requested_address)
        selected = next(
            (
                record
                for record in records
                if record.address == address and record.active
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                "server address is not assigned to an active interface on this "
                f"computer: {requested_address}"
            )
    else:
        candidates = [record for record in records if _is_physical_candidate(record)]
        for route in routes:
            if not isinstance(route, dict):
                continue
            route_interface = route.get("dev")
            preferred_source = route.get("prefsrc")
            if isinstance(preferred_source, str):
                selected = next(
                    (
                        record
                        for record in candidates
                        if str(record.address) == preferred_source
                        and (
                            not isinstance(route_interface, str)
                            or record.interface == route_interface
                        )
                    ),
                    None,
                )
            if selected is None and isinstance(route_interface, str):
                selected = next(
                    (
                        record
                        for record in candidates
                        if record.interface == route_interface
                    ),
                    None,
                )
            if selected is not None:
                break
        if selected is None and candidates:
            selected = candidates[0]
        if selected is None:
            raise ValueError(
                "could not detect a physical LAN IPv4 address; set SERVER_ADDRESS"
            )

    network = selected.network
    if network.prefixlen < 8:
        raise ValueError(f"LAN CIDR is too broad for automatic trust: {network}")
    if requested_cidr:
        network = _parse_ipv4_network(requested_cidr)
        if selected.address not in network:
            raise ValueError(
                f"server address {selected.address} is outside LAN CIDR {network}"
            )
    return str(selected.address), str(network), selected.interface


def _read_ip_json(
    arguments: list[str], *, allow_failure: bool = False
) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", *arguments],
            check=not allow_failure,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise SystemExit("Required command not found: ip") from None
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "ip command failed"
        raise SystemExit(detail) from error
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON returned by ip: {error}") from error
    if not isinstance(payload, list):
        raise SystemExit("unexpected JSON returned by ip")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-address", default="")
    parser.add_argument("--lan-cidr", default="")
    arguments = parser.parse_args()

    routes = _read_ip_json(["route", "get", "1.1.1.1"], allow_failure=True)
    addresses = _read_ip_json(["address", "show", "scope", "global"])
    try:
        server_address, lan_cidr, interface = select_network(
            routes,
            addresses,
            arguments.server_address,
            arguments.lan_cidr,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(server_address, lan_cidr, interface)


if __name__ == "__main__":
    main()

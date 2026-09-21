"""Regression test for domain and risk policy through the running API."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


from tests.support import json_headers


BASE_URL = "http://127.0.0.1:1416"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: test_domain_policy.py <calibration.json>"
        )

    path = Path(sys.argv[1])

    with path.open(
        encoding="utf-8"
    ) as handle:
        cases = json.load(handle)

    passed = 0

    for case in cases:
        request = urllib.request.Request(
            f"{BASE_URL}/classify/run",
            data=json.dumps(
                {
                    "query": case["query"],
                }
            ).encode("utf-8"),
            headers=json_headers(),
        )

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            result = json.load(response)["result"]

        decision = result["decision"]

        expected_domain = case[
            "expected_domain"
        ]
        expected_risk = case[
            "expected_risk"
        ]

        ok = (
            decision["domain"]
            == expected_domain
            and decision["risk"]
            == expected_risk
        )

        if ok:
            passed += 1

        print(
            f"{'PASS' if ok else 'FAIL'} "
            f"expected={expected_domain}/{expected_risk} "
            f"actual={decision['domain']}/{decision['risk']} "
            f"reason={decision['reason']} "
            f"| {case['query']}"
        )

    print()
    print(
        f"passed={passed}/{len(cases)}"
    )

    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

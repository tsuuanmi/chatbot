"""Unit tests for offline authentication."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from chatbot_app.auth import (
    AuthConfigError,
    AuthRegistry,
    AuthenticationContextError,
    AuthIdentity,
    current_identity,
    identity_scope,
)


class AuthRegistryTests(
    unittest.TestCase
):
    def _registry(
        self,
        api_key: str,
        owner_id: str = "owner-a",
    ) -> AuthRegistry:
        digest = hashlib.sha256(
            api_key.encode("utf-8")
        ).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "auth.json"
            )

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "identities": [
                            {
                                "owner_id": owner_id,
                                "api_key_sha256": digest,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            return AuthRegistry.from_file(
                path
            )

    def test_valid_key_resolves_identity(
        self,
    ) -> None:
        api_key = "a" * 40

        registry = self._registry(
            api_key
        )

        identity = registry.authenticate(
            api_key
        )

        self.assertIsNotNone(
            identity
        )
        self.assertEqual(
            identity.owner_id,
            "owner-a",
        )

    def test_invalid_key_is_rejected(
        self,
    ) -> None:
        registry = self._registry(
            "a" * 40
        )

        self.assertIsNone(
            registry.authenticate(
                "b" * 40
            )
        )

    def test_short_key_is_rejected(
        self,
    ) -> None:
        registry = self._registry(
            "a" * 40
        )

        self.assertIsNone(
            registry.authenticate(
                "too-short"
            )
        )

    def test_duplicate_owner_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "auth.json"
            )

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "identities": [
                            {
                                "owner_id": "same",
                                "api_key_sha256": "1" * 64,
                            },
                            {
                                "owner_id": "same",
                                "api_key_sha256": "2" * 64,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )


    def test_missing_registry_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing-auth.json"

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )


    def test_duplicate_digest_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "identities": [
                            {
                                "owner_id": "owner-a",
                                "api_key_sha256": "1" * 64,
                            },
                            {
                                "owner_id": "owner-b",
                                "api_key_sha256": "1" * 64,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )

    def test_non_string_owner_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "identities": [
                            {
                                "owner_id": 123,
                                "api_key_sha256": "1" * 64,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )

    def test_non_string_digest_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"

            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "identities": [
                            {
                                "owner_id": "owner-a",
                                "api_key_sha256": 123,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )

    def test_oversized_registry_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.json"

            path.write_text(
                " " * (256 * 1024 + 1),
                encoding="utf-8",
            )

            with self.assertRaises(
                AuthConfigError
            ):
                AuthRegistry.from_file(
                    path
                )



class IdentityContextTests(
    unittest.TestCase
):
    def test_identity_scope_is_reset(
        self,
    ) -> None:
        with self.assertRaises(
            AuthenticationContextError
        ):
            current_identity()

        identity = AuthIdentity(
            owner_id="owner-a"
        )

        with identity_scope(
            identity
        ):
            self.assertEqual(
                current_identity(),
                identity,
            )

        with self.assertRaises(
            AuthenticationContextError
        ):
            current_identity()


if __name__ == "__main__":
    unittest.main()

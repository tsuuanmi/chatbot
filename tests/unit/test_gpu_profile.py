"""Regression tests for NVIDIA VRAM profiles."""

from __future__ import annotations

import subprocess
import unittest


def profile(
    memory_mib: int,
) -> subprocess.CompletedProcess[str]:
    command = (
        "source offline/lib/gpu.sh; "
        "offline_gpu_profile_for_memory "
        f"{memory_mib}"
    )

    return subprocess.run(
        [
            "bash",
            "-c",
            command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class GPUProfileTests(unittest.TestCase):
    def test_below_6_gib_is_unsupported(
        self,
    ) -> None:
        result = profile(6143)

        self.assertNotEqual(
            result.returncode,
            0,
        )

    def test_6_gib_uses_conservative_profile(
        self,
    ) -> None:
        result = profile(6144)

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "conservative|16|0|6144",
        )

    def test_12_gib_uses_conservative_profile(
        self,
    ) -> None:
        result = profile(12288)

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "conservative|16|0|12288",
        )

    def test_below_16_gib_stays_conservative(
        self,
    ) -> None:
        result = profile(16383)

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "conservative|16|0|16383",
        )

    def test_16_gib_uses_full_profile(
        self,
    ) -> None:
        result = profile(16384)

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "full|99|99|16384",
        )


def headroom(
    total_mib: int,
    used_mib: int,
) -> subprocess.CompletedProcess[str]:
    command = (
        "source offline/lib/gpu.sh; "
        "offline_gpu_memory_headroom_ok "
        f"{total_mib} {used_mib}"
    )

    return subprocess.run(
        [
            "bash",
            "-c",
            command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def residual_limit(
    total_mib: int,
) -> str:
    command = (
        "source offline/lib/gpu.sh; "
        "offline_gpu_residual_limit_mib "
        f"{total_mib}"
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    return result.stdout.strip()


class GPUHeadroomTests(unittest.TestCase):
    def _limit(
        self,
        memory_mib: int,
    ) -> subprocess.CompletedProcess[str]:
        command = (
            "source offline/lib/gpu.sh; "
            "offline_gpu_residual_limit_mib "
            f"{memory_mib}"
        )

        return subprocess.run(
            [
                "bash",
                "-c",
                command,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_6_gib_reserves_one_gib_for_host(
        self,
    ) -> None:
        result = self._limit(6144)

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertEqual(
            result.stdout.strip(),
            "1024",
        )

    def test_8_gib_allows_two_gib_residual(
        self,
    ) -> None:
        result = self._limit(8192)

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertEqual(
            result.stdout.strip(),
            "2048",
        )

    def test_16_gib_uses_capacity_aware_limit(
        self,
    ) -> None:
        result = self._limit(16384)

        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr,
        )

        self.assertEqual(
            result.stdout.strip(),
            "10240",
        )

class GPUResidualMemoryTests(unittest.TestCase):
    @staticmethod
    def shell(command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                (
                    "source offline/lib/gpu.sh; "
                    + command
                ),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_6_gib_residual_limit_is_1_gib(
        self,
    ) -> None:
        result = self.shell(
            "offline_gpu_residual_limit_mib 6144"
        )

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "1024",
        )

    def test_larger_gpu_keeps_6_gib_capacity(
        self,
    ) -> None:
        result = self.shell(
            "offline_gpu_residual_limit_mib 12288"
        )

        self.assertEqual(
            result.returncode,
            0,
        )

        self.assertEqual(
            result.stdout.strip(),
            "6144",
        )

    def test_6_gib_allows_usage_below_limit(
        self,
    ) -> None:
        result = self.shell(
            "offline_gpu_residual_memory_allowed "
            "6144 1023"
        )

        self.assertEqual(
            result.returncode,
            0,
        )

    def test_6_gib_rejects_usage_at_limit(
        self,
    ) -> None:
        result = self.shell(
            "offline_gpu_residual_memory_allowed "
            "6144 1024"
        )

        self.assertNotEqual(
            result.returncode,
            0,
        )

if __name__ == "__main__":
    unittest.main()

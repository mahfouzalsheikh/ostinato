from __future__ import annotations

import unittest

from ostinato.arranger_probe import (
    PROBE_TTL_NS,
    ArrangerProbeError,
    ArrangerProbeRegistry,
    routing_mode_catalog,
)


class ArrangerProbeRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now_ns = 1_000_000_000
        self.registry = ArrangerProbeRegistry(clock=lambda: self.now_ns)

    def test_catalog_distinguishes_native_and_orchestral_parts(self) -> None:
        modes = routing_mode_catalog()

        self.assertEqual(modes[0]["channels"], {"bass": 2, "chord": 3, "drum": 10})
        self.assertEqual(modes[1]["channels"], {"bass": 5, "chord": 6, "drum": 10})
        self.assertEqual(modes[2]["channels"], {"bass": 4, "chord": 4, "drum": 10})

    def test_matching_probes_validate_once(self) -> None:
        channels = {"bass": 2, "chord": 3, "drum": 10}
        tokens = {
            part: self.registry.issue(
                part=part,
                channel=channel,
                output_port="Accordion output",
            )
            for part, channel in channels.items()
        }

        self.registry.validate(
            tokens=tokens,
            channels=channels,
            output_port="Accordion output",
        )
        self.registry.consume(tokens)

        with self.assertRaisesRegex(ArrangerProbeError, "missing or expired"):
            self.registry.validate(
                tokens=tokens,
                channels=channels,
                output_port="Accordion output",
            )

    def test_expired_or_mismatched_probe_is_rejected(self) -> None:
        token = self.registry.issue(
            part="bass", channel=2, output_port="Accordion output"
        )
        self.now_ns += PROBE_TTL_NS + 1

        with self.assertRaisesRegex(ArrangerProbeError, "missing or expired"):
            self.registry.validate(
                tokens={"bass": token, "chord": "missing", "drum": "missing"},
                channels={"bass": 2, "chord": 3, "drum": 10},
                output_port="Accordion output",
            )


if __name__ == "__main__":
    unittest.main()

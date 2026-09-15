"""Hardware-free checks: these do not certify actual display hardware."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dp_cable_test
from dp_core import DPCDReader, analyze_dp, parse_edid


ROOT = Path(__file__).resolve().parents[1]


class HardwareFreeChecks(unittest.TestCase):
    def test_cli_demo_completes_without_display_or_root(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "dp_cable_test.py"), "--demo"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DEMO", result.stdout)
        self.assertIn("HBR3", result.stdout)
        self.assertNotIn("\x1b[", result.stdout)

    def test_demo_never_discovers_hardware(self):
        with patch.object(sys, "argv", ["dp_cable_test.py", "--demo"]), \
             patch.object(dp_cable_test, "find_dp_connections") as discover, \
             patch.object(dp_cable_test, "analyze_dp") as analyze, \
             patch("builtins.print"):
            dp_cable_test.main()
        discover.assert_not_called()
        analyze.assert_not_called()

    def test_missing_aux_reports_unknown_device(self):
        with tempfile.TemporaryDirectory() as folder:
            analysis = analyze_dp(str(Path(folder) / "missing"), "test-DP-1", None)
        self.assertTrue(analysis.issues)
        self.assertEqual(analysis.dp_version, "Bilinmiyor")
        self.assertEqual(analysis.max_link_rate_gbps, 0)
        self.assertEqual(analysis.max_resolutions, [])

    def test_edid_rejects_truncation_and_invalid_header(self):
        for raw in (b"", b"\x00\xff\xff\xff\xff\xff\xff\x00" + bytes(119), bytes(128)):
            with self.subTest(length=len(raw)):
                self.assertIsNone(parse_edid(raw))

    def test_aux_reads_requested_offset_and_handles_end_of_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic-aux"
            source.write_bytes(bytes([0x14, 0x1E, 0x84]))
            reader = DPCDReader(str(source))
            self.assertEqual(reader.read_bytes(1, 2), [0x1E, 0x84])
            self.assertIsNone(reader.read_byte(100))


if __name__ == "__main__":
    unittest.main()

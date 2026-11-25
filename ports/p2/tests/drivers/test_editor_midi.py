"""Boundaries, interrupted saves, aborts and MIDI framing without a board."""

import sys
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PACKAGES = Path(__file__).resolve().parents[2] / "packages"
sys.path[:0] = [str(PACKAGES / "p2edit"), str(PACKAGES / "p2midi")]
import p2edit
import p2midi


class Packages(unittest.TestCase):
    def test_failed_rename_restores_original_and_keeps_edits_for_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            previous = os.getcwd()
            try:
                os.chdir(temp)
                name = Path(temp, "demo.py").as_posix()
                if os.name == "nt":
                    name = name[2:]
                Path(name).write_bytes(b"original\n")
                do_rename = os.rename
                first = True

                def fail_once(src, dst):
                    nonlocal first
                    if first and src.endswith(".new"):
                        first = False
                        self.assertEqual(Path(name + ".bak").read_bytes(), b"original\n")
                        raise OSError("test rename failure")
                    return do_rename(src, dst)

                with patch("p2edit._readline", side_effect=["r 1 updated", "w", "w"]), patch(
                    "p2edit.os.rename", side_effect=fail_once
                ):
                    self.assertTrue(p2edit.edit(name))
                self.assertEqual(Path(name).read_bytes(), b"updated\n")
                self.assertFalse(Path(name + ".bak").exists())
                self.assertFalse(Path(name + ".new").exists())
            finally:
                os.chdir(previous)

    def test_oversized_command_is_rejected_as_a_whole(self):
        stream = io.TextIOWrapper(io.BytesIO(b"a " + b"x" * 4300 + b"\rq\r"))
        output = io.TextIOWrapper(io.BytesIO())
        with patch("sys.stdin", stream), patch("sys.stdout", output):
            self.assertEqual(p2edit._readline("> "), "q")

    def test_edit_commit_abort_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "draft.py"
            # The embedded editor accepts absolute Unix-style VFS paths.
            import os

            previous = os.getcwd()
            try:
                if os.name == "nt":
                    os.chdir(temp)
                    filename = path.as_posix()[2:]
                else:
                    filename = str(path)
                with patch(
                    "p2edit._readline", side_effect=["a first", "a second", "r 2 démo", "d 1", "w"]
                ):
                    self.assertTrue(p2edit.edit(filename))
                self.assertEqual(path.read_bytes(), "démo\n".encode())
                with patch("p2edit._readline", side_effect=["d 1", "q"]):
                    self.assertFalse(p2edit.edit(filename))
                backup = Path(filename + ".bak")
                backup.write_bytes(b"recovery copy")
                with self.assertRaises(OSError):
                    p2edit._save(filename, ["new"])
                self.assertEqual(backup.read_bytes(), b"recovery copy")
                self.assertEqual(path.read_bytes(), "démo\n".encode())
            finally:
                os.chdir(previous)

    def test_midi_channel_and_short_write(self):
        class UART:
            def write(self, packet):
                self.packet = packet
                return self.length

        uart = UART()
        uart.length = 3
        midi = p2midi.MidiOut(uart, 16)
        midi.note_on(60)
        self.assertEqual(uart.packet, bytes((159, 60, 100)))
        with self.assertRaises(ValueError):
            midi.control(1, 128)
        uart.length = 2
        with self.assertRaises(OSError):
            midi.note_off(60)
        with self.assertRaises(ValueError):
            p2midi.MidiOut(uart, 0)


if __name__ == "__main__":
    unittest.main()

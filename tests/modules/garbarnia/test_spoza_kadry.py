"""W7e-2b: funkcja awaryjna „Dodaj spoza kadry” (wspólna treść: tests/modules/spoza_kadry.py)."""
import unittest
import harness
import spoza_kadry

APP, TMP = harness.boot("garbarnia")


class SpozaKadryTests(spoza_kadry.make(APP, "garbarnia")):
    pass


class SpozaKadryPanelTests(spoza_kadry.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

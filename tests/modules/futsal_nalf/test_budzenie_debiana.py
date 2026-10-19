"""E2d3a: budzenie Debiana przez HUB (wspolna tresc: tests/modules/budzenie_debiana.py)."""
import unittest
import harness
import budzenie_debiana

APP, TMP = harness.boot("futsal_nalf")


class BudzenieDebiana(budzenie_debiana.make(APP)):
    pass


if __name__ == "__main__":
    unittest.main()

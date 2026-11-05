"""W8a, C: reguły zmiany statusu meczu z zakładki MECZE (wspólna treść: tests/modules/zmiana_statusu.py)."""
import unittest
import harness
import zmiana_statusu

APP, TMP = harness.boot("futsal_nalf")


class ZmianaStatusuTests(zmiana_statusu.make(APP, "futsal_nalf")):
    pass


if __name__ == "__main__":
    unittest.main()

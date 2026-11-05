"""W8a, C: reguły zmiany statusu meczu z zakładki MECZE (wspólna treść: tests/modules/zmiana_statusu.py)."""
import unittest
import harness
import zmiana_statusu

APP, TMP = harness.boot("garbarnia")


class ZmianaStatusuTests(zmiana_statusu.make(APP, "garbarnia")):
    pass


if __name__ == "__main__":
    unittest.main()

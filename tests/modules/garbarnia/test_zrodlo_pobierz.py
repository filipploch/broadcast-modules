"""W8a2: Pobierz ze źródła (wspólna treść: tests/modules/zrodlo_pobierz.py)."""
import unittest
import harness
import zrodlo_pobierz

APP, TMP = harness.boot("garbarnia")


class ZrodloPobierzTests(zrodlo_pobierz.make(APP, "garbarnia")):
    pass


class ZrodloPobierzNodeTests(zrodlo_pobierz.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

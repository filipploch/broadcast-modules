"""W7e-2a: zapis składu meczowego (wspólna treść: tests/modules/zapis_skladu.py)."""
import unittest
import harness
import zapis_skladu

APP, TMP = harness.boot("garbarnia")


class ZapisSkladuTests(zapis_skladu.make(APP, "garbarnia")):
    pass


if __name__ == "__main__":
    unittest.main()

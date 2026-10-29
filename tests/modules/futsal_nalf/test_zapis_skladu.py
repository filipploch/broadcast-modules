"""W7e-2a: zapis składu meczowego (wspólna treść: tests/modules/zapis_skladu.py)."""
import unittest
import harness
import zapis_skladu

APP, TMP = harness.boot("futsal_nalf")


class ZapisSkladuTests(zapis_skladu.make(APP, "futsal_nalf")):
    pass


if __name__ == "__main__":
    unittest.main()

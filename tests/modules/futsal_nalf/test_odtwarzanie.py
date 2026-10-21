"""E2e: odtwarzanie po awarii (wspolna tresc: tests/modules/odtwarzanie.py)."""
import unittest
import harness
import odtwarzanie

APP, TMP = harness.boot("futsal_nalf")

_Odtwarzanie = odtwarzanie.make(APP)


class Odtwarzanie(_Odtwarzanie):
    pass


del _Odtwarzanie


if __name__ == "__main__":
    unittest.main()

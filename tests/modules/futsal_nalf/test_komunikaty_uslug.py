"""E2d2: komunikaty uslug w panelu (wspolna tresc: tests/modules/komunikaty_uslug.py)."""
import unittest
import harness
import komunikaty_uslug

APP, TMP = harness.boot("futsal_nalf")

(_Komunikaty,) = komunikaty_uslug.make(APP)


class KomunikatyUslug(_Komunikaty):
    pass


del _Komunikaty


if __name__ == "__main__":
    unittest.main()

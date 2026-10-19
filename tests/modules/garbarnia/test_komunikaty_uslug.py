"""E2d2: komunikaty uslug w panelu (wspolna tresc: tests/modules/komunikaty_uslug.py)."""
import unittest
import harness
import komunikaty_uslug

APP, TMP = harness.boot("garbarnia")

_Komunikaty, _Nakladka = komunikaty_uslug.make(APP)


class KomunikatyUslug(_Komunikaty):
    pass


class RestartNakladki(_Nakladka):
    pass


del _Komunikaty, _Nakladka


if __name__ == "__main__":
    unittest.main()

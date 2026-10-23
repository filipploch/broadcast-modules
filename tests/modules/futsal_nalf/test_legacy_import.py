"""I0: blokada dotychczasowego pobierania ze stron (wspolna tresc: tests/modules/legacy_import.py)."""
import unittest
import harness
import legacy_import

APP, TMP = harness.boot("futsal_nalf")

_Blokada = legacy_import.make(APP)


class BlokadaPobierania(_Blokada):
    pass


del _Blokada


if __name__ == "__main__":
    unittest.main()

"""Panel bez otwartej sesji: zdarzenia Socket.IO i strony nie rzucaja wyjatkow (wspolna tresc: tests/modules/bez_sesji.py)."""
import unittest
import harness
import bez_sesji

APP, TMP = harness.boot("futsal_nalf")


class BezSesji(bez_sesji.make(APP)):
    pass


if __name__ == "__main__":
    unittest.main()

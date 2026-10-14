"""E2d2: status sesji zglaszany HUB-owi (wspolna tresc: tests/modules/status_sesji.py)."""
import unittest
import harness
import status_sesji

APP, TMP = harness.boot("futsal_nalf")

(_Status,) = status_sesji.make(APP)


class StatusSesji(_Status):
    pass


del _Status


if __name__ == "__main__":
    unittest.main()

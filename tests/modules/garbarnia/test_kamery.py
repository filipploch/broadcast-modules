"""E2d3b: nadzór nad kamerami (wspolna tresc: tests/modules/kamery.py)."""
import unittest
import harness
import kamery

APP, TMP = harness.boot("garbarnia")

_Kamery = kamery.make(APP)


class Kamery(_Kamery):
    pass


del _Kamery


if __name__ == "__main__":
    unittest.main()

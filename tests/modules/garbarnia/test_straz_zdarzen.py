"""E2d1: straz zdarzen, recording_command, leniwa inicjalizacja (wspolna tresc: tests/modules/straz_zdarzen.py)."""
import unittest
import harness
import straz_zdarzen

APP, TMP = harness.boot("garbarnia")

_Straz, _Rec, _Leniwa = straz_zdarzen.make(APP)


class StrazZdarzen(_Straz):
    pass


class RecordingCommand(_Rec):
    pass


class LeniwaInicjalizacja(_Leniwa):
    pass


del _Straz, _Rec, _Leniwa


if __name__ == "__main__":
    unittest.main()

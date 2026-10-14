"""E2d1: modul uruchamiany przez HUB (wspolna tresc: tests/modules/hub_uruchamia_modul.py)."""
import unittest
import harness
import hub_uruchamia_modul

APP, TMP = harness.boot("garbarnia")

_Logi, _Ustawienia, _Zamkniecie = hub_uruchamia_modul.make(APP)


class LogiPrzezHub(_Logi):
    pass


class UstawieniaZHuba(_Ustawienia):
    pass


class ZamkniecieNaProsbeHuba(_Zamkniecie):
    pass


del _Logi, _Ustawienia, _Zamkniecie     # bazowe klasy nie sa osobnymi testami


if __name__ == "__main__":
    unittest.main()

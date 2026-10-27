"""W7a: pobieranie pary (liga, sezon) z WP do bazy modulu (wspolna tresc: tests/modules/wp_pobieranie.py)."""
import unittest
import harness
import wp_pobieranie

APP, TMP = harness.boot("futsal_nalf")

_Pierwsze, _Reguly, _Krawedzie, _Panel, _Nazwy = wp_pobieranie.make(APP)


class PierwszePobranieTests(_Pierwsze):
    pass


class ReguleMeczowTests(_Reguly):
    pass


class KrawedzieIAwarieTests(_Krawedzie):
    pass


class TrasaIPanelTests(_Panel):
    pass


class NazwyZWpTests(_Nazwy):
    pass


del _Pierwsze, _Reguly, _Krawedzie, _Panel, _Nazwy


if __name__ == "__main__":
    unittest.main()

"""E2c: kontekst w poleceniach do pluginow i filtr spoznionych komunikatow (wspolna tresc: tests/modules/kontekst.py)."""
import unittest
import harness
import kontekst

APP, TMP = harness.boot("garbarnia")


class Kontekst(kontekst.make(APP)):
    pass


if __name__ == "__main__":
    unittest.main()

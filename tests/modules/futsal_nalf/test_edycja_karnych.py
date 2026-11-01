"""W8a: wynik rzutów karnych z formularza edycji meczu (wspólna treść: tests/modules/edycja_karnych.py)."""
import unittest
import harness
import edycja_karnych

APP, TMP = harness.boot("futsal_nalf")


class EdycjaKarnychTests(edycja_karnych.make(APP, "futsal_nalf")):
    pass


if __name__ == "__main__":
    unittest.main()

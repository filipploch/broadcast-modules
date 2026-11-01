"""W8a: wynik rzutów karnych z formularza edycji meczu (wspólna treść: tests/modules/edycja_karnych.py)."""
import unittest
import harness
import edycja_karnych

APP, TMP = harness.boot("garbarnia")


class EdycjaKarnychTests(edycja_karnych.make(APP, "garbarnia")):
    pass


if __name__ == "__main__":
    unittest.main()

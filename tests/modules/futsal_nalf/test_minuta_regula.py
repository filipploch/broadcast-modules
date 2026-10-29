"""Reguła minuty zdarzenia (krok B2): ładunki z początkiem okresu i tabela przypadków na prawdziwym kodzie nakładek (wspólna treść: tests/modules/minuta_ladunki.py)."""
import unittest
import harness
import minuta_ladunki

APP, TMP = harness.boot("futsal_nalf")


class LadunkiMinutyTests(minuta_ladunki.make(APP, "futsal_nalf")):
    pass


class RegulaMinutyNodeTests(minuta_ladunki.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

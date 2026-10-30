"""W7f-null: nakładki nie pokazują null/undefined/NaN/None (wspólna treść: tests/modules/nakladki_null.py)."""
import unittest
import nakladki_null


class NakladkiNullTests(nakladki_null.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

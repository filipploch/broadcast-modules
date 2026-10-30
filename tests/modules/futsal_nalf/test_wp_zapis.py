"""W8a: zapis stanu i wyniku meczu do WP (wspólna treść: tests/modules/wp_zapis.py)."""
import unittest
import harness
import wp_zapis

APP, TMP = harness.boot("futsal_nalf")


class ZapisDoWpTests(wp_zapis.make(APP, "futsal_nalf")):
    pass


class WpZapisUiTests(wp_zapis.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

"""W8a: zapis stanu i wyniku meczu do WP (wspólna treść: tests/modules/wp_zapis.py)."""
import unittest
import harness
import wp_zapis

APP, TMP = harness.boot("garbarnia")


class ZapisDoWpTests(wp_zapis.make(APP, "garbarnia")):
    pass


class WpZapisUiTests(wp_zapis.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

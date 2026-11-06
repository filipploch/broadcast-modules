"""W8b: tabela z WP w module (wspólna treść: tests/modules/wp_tabela.py)."""
import unittest
import harness
import wp_tabela

APP, TMP = harness.boot("garbarnia")


class WpTabelaTests(wp_tabela.make(APP, "garbarnia")):
    pass


class WpTabelaNodeTests(wp_tabela.make_node()):
    pass


if __name__ == "__main__":
    unittest.main()

"""WP-2: polaczenie z WP modulu, lista rozgrywek i rozgrywki domyslne (wspolna tresc: tests/modules/wp_rozgrywki.py)."""
import unittest
import harness
import wp_rozgrywki

APP, TMP = harness.boot("futsal_nalf")

_Config, _Lista, _Manager, _Panel = wp_rozgrywki.make(APP)


class WpConfigTests(_Config):
    pass


class WpListTests(_Lista):
    pass


class WpManagerTests(_Manager):
    pass


class WpPanelTests(_Panel):
    pass


del _Config, _Lista, _Manager, _Panel


if __name__ == "__main__":
    unittest.main()

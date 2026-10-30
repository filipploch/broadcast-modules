"""W7f-null: nakładki nie pokazują tekstów null/undefined/NaN/None (displayText). Prawdziwy kod obu nakładek w atrapie przeglądarki (tests/modules/js/nakladki_null_test.js):
funkcja displayText (0 i false bez zmian), kompletne dane = wzorzec z commitu sprzed zmiany (tests/modules/js/nakladki_wzorzec.json), mutacje każdego pola komunikatu."""
import shutil
import subprocess
import unittest
from pathlib import Path


def make_node():
    class NakladkiNullNode(unittest.TestCase):
        def test_nakladki_nie_pokazuja_null_undefined_nan_none(self):
            node = shutil.which('node')
            if node is None:
                raise RuntimeError('Brak Node.js w PATH')
            skrypt = Path(__file__).resolve().parent / 'js' / 'nakladki_null_test.js'
            r = subprocess.run([node, str(skrypt)], capture_output=True, text=True, encoding='utf-8', timeout=600)
            self.assertEqual(r.returncode, 0, r.stdout[-6000:] + r.stderr[-2000:])
            self.assertIn('OK displayText', r.stdout)

    return NakladkiNullNode

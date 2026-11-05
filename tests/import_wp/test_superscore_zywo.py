"""W8a: prawdziwe odpowiedzi Superscore z meczu w toku (tests/import_wp/dane/superscore_zywo.json, 2026-11-01, A-League Kobiety): mapowanie stanu i wyniku
na żywo, zgodność odpowiedzi meczu (overview) z odpowiedzią sezonu, obecność live_minute (poza zakresem 12.11: tylko stwierdzamy, że importer go nie używa)."""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'import_wp'))
import superscore  # noqa: E402

Z = json.loads((Path(__file__).resolve().parent / 'dane' / 'superscore_zywo.json').read_text(encoding='utf-8'))


class ZywoZPrawdziwegoZrodlaTests(unittest.TestCase):
    def test_stany_i_wynik_na_zywo_sa_mapowane_na_trasy_source_state(self):
        n = lambda e: superscore.norm_mecz(e, 'liga', 'sezon')
        self.assertEqual(n(Z['trwajace'])['zywo'], {'stan': 'trwa', 'wynik': (1, 0), 'status': 7, 'nietypowy': False})
        self.assertEqual(n(Z['zakonczone'])['zywo'], {'stan': 'zakonczony', 'wynik': (0, 2), 'status': 100, 'nietypowy': False})
        self.assertEqual(n(Z['nierozpoczete'])['zywo'], {'stan': 'nierozpoczety', 'wynik': None, 'status': 0, 'nietypowy': False})
        self.assertEqual(n(Z['trwajace'])['results'], {})                      # mecz w toku nie dostaje natywnego wyniku końcowego

    def test_wlasciwosci_meczu_w_toku_w_prawdziwej_odpowiedzi(self):
        e = Z['trwajace']
        self.assertEqual((e['match_state'], e['match_status']), (1, 7))
        self.assertEqual({s['type'] for s in e['scores']}, {0, 1, 2, 6})
        self.assertEqual(Z['zakonczone']['match_status'], 100)
        self.assertEqual(Z['nierozpoczete']['scores'], [])
        self.assertEqual(set(e['live_minute']), {'extra_seconds', 'anchor_date', 'elapsed_seconds', 'max_seconds'})
        self.assertIsNone(Z['zakonczone']['live_minute'])
        self.assertIsNone(Z['nierozpoczete']['live_minute'])

    def test_odpowiedz_meczu_ma_te_same_pola_stanu_i_wyniku_co_odpowiedz_sezonu(self):
        ov, e = Z['overview_trwajacy'], Z['trwajace']
        self.assertEqual(ov['id'], e['id'])
        for k in ('match_state', 'match_status', 'scores'):
            self.assertEqual(ov[k], e[k], k)
        self.assertEqual(superscore._zywo(ov), superscore._zywo(e))


if __name__ == '__main__':
    unittest.main()

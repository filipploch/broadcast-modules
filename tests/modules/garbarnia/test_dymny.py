"""Test dymny (E1): wszystkie trasy GET bez parametrow nie moga konczyc sie bledem serwera, ani bez sesji, ani z aktywnym meczem."""
import unittest
import harness

APP, TMP = harness.boot("garbarnia")

# trasy, ktore z natury wymagaja HUB-a, OBS-a albo sieci (nie dotycza sesji); pomijane
POMIN = ("/api/obs", "/api/hub", "/api/scraper", "/api/replay-export", "/static", "/api/helper", "/api/gopro", "/api/servo")


def _trasy():
    out = []
    for rule in APP.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and not rule.rule.startswith(POMIN):
            out.append(rule.rule)
    return sorted(set(out))


class Dymny(unittest.TestCase):
    def setUp(self):
        harness.reset_db(APP)
        self.ids = harness.seed(APP)
        self.client = APP.test_client()

    def _sprawdz(self, etykieta):
        bledy = []
        for url in _trasy():
            try:
                r = self.client.get(url)
                if r.status_code >= 500:
                    bledy.append((url, r.status_code))
            except Exception as e:                      # nieobsluzony wyjatek w trasie
                bledy.append((url, f"{type(e).__name__}: {str(e)[:80]}"))
        self.assertEqual(bledy, [], f"{etykieta}: trasy z bledem serwera")

    def test_bez_sesji(self):
        self._sprawdz("bez sesji")

    def test_z_aktywnym_meczem(self):
        self.client.get(f"/games/{self.ids['g1']}/prepare-broadcast")
        self.client.get(f"/games/{self.ids['g1']}/select-broadcast")
        self._sprawdz("z aktywnym meczem")


if __name__ == "__main__":
    unittest.main()

"""Zapis znormalizowanych danych ze źródła do WP/SportsPressa: powtarzalny (upsert) po identyfikatorze ze źródła.

Każdy zapisany rekord (drużyna, zawodnik, mecz) ma w WP pola własne bm_source, bm_source_id i bm_source_hash (wtyczka bm-pomocnik).
Przy kolejnym imporcie rekord jest dopasowywany po (źródło, identyfikator); gdy skrót treści się nie zmienił, nic nie jest wysyłane.
Nic nie jest usuwane: rekordy, których nie ma już w źródle, trafiają do raportu. Mecz z bm_locked albo bm_live jest pomijany.
Liga i sezon (kategorie SportsPressa) są dopasowywane po slugu nadawanym przez importer: <źródło>-l<id> i <źródło>-s<id>."""
import hashlib
import html
import json

WERSJA_IMPORTU = 1        # zmiana sposobu budowania rekordów wymusza ponowny zapis (wchodzi do skrótu)
STATUSY = 'publish,future,draft,pending,private'


def nazwa_do_porownania(tekst):
    return ' '.join(html.unescape(tekst or '').casefold().split())


def _z_meta(cialo, meta):
    """Treść żądania: pole '_meta' z budowniczego (dodatkowe pola własne rekordu) trafia do meta obok pól importu."""
    cialo = dict(cialo)
    dodatkowe = cialo.pop('_meta', {})
    return {**cialo, 'meta': {**meta, **dodatkowe}}


def skrot(payload):
    surowe = json.dumps([WERSJA_IMPORTU, payload], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(surowe.encode('utf-8')).hexdigest()


class MapaId(dict):
    """Mapa identyfikator ze źródła -> id w WP; klucze porównywane jako tekst (NALF ma id liczbowe, Superscore tekstowe)."""

    def __getitem__(self, k):
        return super().__getitem__(str(k))

    def __setitem__(self, k, v):
        super().__setitem__(str(k), v)

    def __contains__(self, k):
        return super().__contains__(str(k))

    def get(self, k, default=None):
        return super().get(str(k), default)


class Licznik:
    def __init__(self):
        self.nowe = self.zmienione = self.bez_zmian = self.pominiete = self.bledy = 0
        self.nie_ma_w_zrodle = []
        self.uwagi = []
        self.duplikaty = []

    def linia(self):
        return (f'{self.nowe} nowych, {self.zmienione} zmienionych, {self.bez_zmian} bez zmian, {self.pominiete} pominiętych, '
                f'{self.bledy} błędów')


class Import:
    def __init__(self, wp, zrodlo='nalf', na_sucho=False, log=print):
        self.wp = wp
        self.zrodlo = zrodlo
        self.na_sucho = na_sucho
        self.log = log
        self.liczniki = {'ligi': Licznik(), 'sezon': Licznik(), 'druzyny': Licznik(), 'zawodnicy': Licznik(), 'mecze': Licznik()}
        self.id_wp = {k: MapaId() for k in ('ligi', 'sezon', 'druzyny', 'zawodnicy', 'mecze')}   # id ze źródła -> id w WP
        self.istniejace = {}
        self.niepewne_nazwiska = []

    # -- kategorie (liga, sezon)
    def _slug(self, rodzaj, src_id):
        return f'{self.zrodlo}-{"l" if rodzaj == "ligi" else "s"}{src_id}'.lower()      # WP zapisuje slugi małymi literami (id Superscore ma wielkie)

    def kategorie(self, rodzaj, elementy):
        """Zapewnia ligę/sezon w WP (po slugu). Zwraca {id ze źródła: id w WP}. Na sucho: brakujące dostają id 0."""
        trasa = 'sportspress/v2/' + ('leagues' if rodzaj == 'ligi' else 'seasons')
        licz = self.liczniki[rodzaj]
        mapa = {t['slug'].lower(): t for t in self.wp.pobierz_wszystko(trasa, {'_fields': 'id,name,slug'})}
        for src in elementy:
            slug = self._slug(rodzaj, src['id'])
            if slug in mapa:
                licz.bez_zmian += 1
                self.id_wp[rodzaj][src['id']] = mapa[slug]['id']
            elif self.na_sucho:
                licz.nowe += 1
                self.id_wp[rodzaj][src['id']] = 0
            else:
                nowy = self.wp.utworz(trasa, {'name': src['name'], 'slug': slug})
                licz.nowe += 1
                self.id_wp[rodzaj][src['id']] = nowy['id']
        return self.id_wp[rodzaj]

    # -- istniejące rekordy
    def wczytaj_istniejace(self, rodzaj, trasa):
        wynik = {}
        pola = 'id,meta,title,teams' if rodzaj == 'zawodnicy' else 'id,meta'      # nazwa i drużyny zawodnika: wykrywanie duplikatów
        for r in self.wp.pobierz_wszystko(trasa, {'_fields': pola, 'status': STATUSY}):
            meta = r.get('meta') or {}
            if meta.get('bm_source') == self.zrodlo and meta.get('bm_source_id'):
                tytul = r.get('title')
                tytul = tytul.get('rendered') if isinstance(tytul, dict) else tytul
                wynik[str(meta['bm_source_id'])] = {'id': r['id'], 'hash': meta.get('bm_source_hash') or '',
                                                    'zablokowany': bool(meta.get('bm_locked')) or bool(meta.get('bm_live')),
                                                    'nazwa': nazwa_do_porownania(tytul), 'teams': [int(t) for t in r.get('teams') or [] if t],
                                                    'imie': meta.get('bm_first_name') or '', 'nazwisko': meta.get('bm_last_name') or '',
                                                    'skrot': meta.get('bm_short_name') or ''}
        self.istniejace[rodzaj] = wynik
        return wynik

    def upsert(self, rodzaj, trasa, src_id, payload, buduj_body, przed_aktualizacja=None):
        """Tworzy albo aktualizuje rekord; zwraca id w WP (0 na sucho dla nowych). buduj_body() wołane tylko, gdy trzeba zapisać; przed_aktualizacja(id_wp) czyści stare dane rekordu (mecz)."""
        licz = self.liczniki[rodzaj]
        h = skrot(payload)
        ist = self.istniejace[rodzaj].get(str(src_id))
        meta = {'bm_source': self.zrodlo, 'bm_source_id': str(src_id), 'bm_source_hash': h}
        try:
            if ist is None:
                licz.nowe += 1
                if self.na_sucho:
                    self.id_wp[rodzaj][src_id] = 0
                    return 0
                cialo = buduj_body()
                nowy = self.wp.utworz(trasa, _z_meta(cialo, meta))
                self.id_wp[rodzaj][src_id] = nowy['id']
                return nowy['id']
            self.id_wp[rodzaj][src_id] = ist['id']
            if ist['zablokowany']:
                licz.pominiete += 1
                licz.uwagi.append(f'{rodzaj} {src_id}: pominięty (blokada wyniku albo mecz trwa)')
                return ist['id']
            if ist['hash'] == h:
                licz.bez_zmian += 1
                return ist['id']
            licz.zmienione += 1
            if not self.na_sucho:
                if przed_aktualizacja:
                    przed_aktualizacja(ist['id'])
                self.wp.zaktualizuj(trasa, ist['id'], _z_meta(buduj_body(), meta))
            return ist['id']
        except Exception as e:                              # jeden zły rekord nie przerywa całego importu
            licz.bledy += 1
            licz.uwagi.append(f'{rodzaj} {src_id}: {e}')
            self.log(f'  BŁĄD {rodzaj} {src_id}: {e}')
            return self.id_wp[rodzaj].get(src_id, 0)

    def wykryj_duplikaty_zawodnikow(self, zawodnicy_zrodla):
        """Zawodnik o tej samej nazwie i drużynie, ale z innym identyfikatorem źródła niż rekord już będący w WP (a nieobecny w źródle):
        typowo Superscore zmieniło zawodnikowi identyfikator (np. fake:player:<uuid>). Import nie usuwa starego rekordu, tylko to zgłasza."""
        licz = self.liczniki['zawodnicy']
        stare = self.istniejace.get('zawodnicy', {})
        w_zrodle = {str(p['id']) for p in zawodnicy_zrodla}
        osieroceni = {sid: ist for sid, ist in stare.items() if sid not in w_zrodle}
        if not osieroceni:
            return
        for p in zawodnicy_zrodla:
            nazwa = nazwa_do_porownania(p['name'])
            druzyny = {self.id_wp['druzyny'].get(t) for t in p['teams']} - {None, 0}
            for sid, ist in osieroceni.items():
                if ist['nazwa'] == nazwa and druzyny & set(ist['teams']):
                    licz.duplikaty.append(f'{p["name"]}: nowy identyfikator {p["id"]}, w WP jest też rekord ze starym identyfikatorem {sid} (id WP {ist["id"]})')

    def raportuj_brakujace(self, rodzaj, ids_zrodla):
        licz = self.liczniki[rodzaj]
        licz.nie_ma_w_zrodle = sorted(set(self.istniejace.get(rodzaj, {})) - {str(i) for i in ids_zrodla})

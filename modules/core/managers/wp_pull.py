"""Pobieranie jednej pary (liga, sezon) z WP do bazy modułu (W7a, plan: docs/plan-W7-odczyt-z-wp.md).

- Dane z WP czytane są w całości przed jakimkolwiek zapisem (zerwane połączenie = baza nietknięta).
- Ta sama procedura robi podgląd (apply=False: niczego nie zapisuje, nowe rekordy to atrapy z ujemnym id) i zapis (apply=True: jedna
  transakcja, przed nią kopia pliku bazy w instance/kopie-wp, ostatnie 5). Zapis zawsze poprzedza podgląd, więc raport z zapisu zgadza się z podglądem.
- Nigdy nie usuwa: rekordy modułu powiązane z WP, których WP już nie ma, trafiają do raportu.
- Powiązania z WP: istniejące tabele *_foreign_ids ze źródłem „wp” (folder wp); klucz to numer rekordu w WP, dla ligi „liga:sezon”.
- Mecz trwający lub rozpoczęty w module nie jest zmieniany; zakończony dostaje korekty z WP (jawnie w raporcie); WP bez wyniku nie kasuje wyniku modułu.
- Mecz z drużyną „Do ustalenia” (id 0) nie jest wczytywany i nie powstaje drużyna; raport podaje ich liczbę."""
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core.managers.wp_client import WpError
from core.utils.wp_names import nazwa_14, numer_rundy, podziel_nazwisko_imie, tekst, wylicz_unikalne

SCRAPER_NAME = 'WordPress/SportsPress'
SCRAPER_FOLDER = 'wp'
KOPIE_DIR = 'kopie-wp'
KOPII_ZACHOWANYCH = 5
LIMIT_LISTY = 200                  # dłuższe listy w raporcie są ucinane (liczniki zostają dokładne)
LOGO_PREFIX = 'static/images/logos/'

_lock = threading.Lock()


def _kat_licznik():
    return {'dodano': 0, 'zaktualizowano': 0, 'bez_zmian': 0, 'pominieto': 0}


def kanoniczna_sciezka_logo(sciezka):
    """'/static//images/logos/x/y.png' -> 'static/images/logos/x/y.png' (bez początkowego ukośnika, pojedyncze ukośniki)."""
    return re.sub(r'/+', '/', (sciezka or '').strip().replace('\\', '/')).lstrip('/')


def pobierz_dane_pary(client, league_id, season_id):
    """Czyta z WP wszystko, co potrzebne dla pary. Zgłasza WpError. Nic nie zapisuje."""
    status = 'publish,future' if client.cfg.has_auth else 'publish'
    liga = next((x for x in client.get_all('sportspress/v2/leagues', {'_fields': 'id,name,slug'}) if int(x['id']) == int(league_id)), None)
    sezon = next((x for x in client.get_all('sportspress/v2/seasons', {'_fields': 'id,name,slug'}) if int(x['id']) == int(season_id)), None)
    if liga is None or sezon is None:
        raise WpError('format', 'tych rozgrywek nie ma już w WP (odśwież listę)')
    kat = {'leagues': int(league_id), 'seasons': int(season_id), 'status': status}
    druzyny = client.get_all('sportspress/v2/teams', {**kat, '_fields': 'id,title,meta,abbreviation'})
    # kadra całej drużyny w sezonie (bez ograniczenia do ligi: drużyna gra w kilku ligach, a w module ma jedną kadrę); zawodnicy bez drużyny pary
    # są odrzucani przy zapisie
    zawodnicy = client.get_all('sportspress/v2/players', {'seasons': int(season_id), 'status': status, '_fields': 'id,title,number,teams,current_teams,past_teams,meta'})
    mecze = client.get_all('sportspress/v2/events', {**kat, '_fields': 'id,date,status,title,teams,main_results,day,meta'})
    znane = {int(d['id']) for d in druzyny}
    # drużyna z meczu pary, której WP nie oznaczył kategorią pary: dociągamy po numerze (gra w tej lidze, więc należy do pary)
    dodatkowe = []
    mecze_druzyny = {int(t) for m in mecze for t in (m.get('teams') or []) if t}
    potrzebne = sorted(mecze_druzyny - znane)
    if potrzebne:
        dodatkowe = client.get_all('sportspress/v2/teams', {'include': ','.join(map(str, potrzebne)), 'status': status,
                                                           '_fields': 'id,title,meta,abbreviation'})
    return {'liga': liga, 'sezon': sezon, 'druzyny': druzyny + dodatkowe, 'zawodnicy': zawodnicy, 'mecze': mecze,
            'pobrano': datetime.now().isoformat(timespec='seconds')}


class Pobieranie:
    """Jedno wykonanie: podgląd albo zapis. Obiekt jednorazowy."""

    def __init__(self, db, dane, logo_root, logo_folder, apply):
        from core.models.base_broadcast_session import get_broadcast_session_model, get_session_game_model
        from core.models.base_game import get_game_model
        from core.models.base_game_event import get_game_event_model
        from core.models.base_game_foreign_id import get_game_foreign_id_model
        from core.models.base_game_player import get_game_player_model
        from core.models.base_game_timer import get_game_timer_model
        from core.models.base_league import get_league_model
        from core.models.base_league_foreign_id import get_league_foreign_id_model
        from core.models.base_league_team import get_league_team_model
        from core.models.base_period import get_period_model
        from core.models.base_player import get_player_model
        from core.models.base_player_foreign_id import get_player_foreign_id_model
        from core.models.base_scraper import get_scraper_model
        from core.models.base_season import get_season_model
        from core.models.base_season_foreign_id import get_season_foreign_id_model
        from core.models.base_stadium import get_stadium_model
        from core.models.base_team import get_team_model
        from core.models.base_team_foreign_id import get_team_foreign_id_model
        self.m = SimpleNamespace(
            Session=get_broadcast_session_model(), SessionGame=get_session_game_model(), Game=get_game_model(), GameEvent=get_game_event_model(),
            GameForeignId=get_game_foreign_id_model(), GamePlayer=get_game_player_model(), GameTimer=get_game_timer_model(), League=get_league_model(),
            LeagueForeignId=get_league_foreign_id_model(), Stadium=get_stadium_model(), LeagueTeam=get_league_team_model(), Period=get_period_model(),
            Player=get_player_model(), PlayerForeignId=get_player_foreign_id_model(), Scraper=get_scraper_model(), Season=get_season_model(),
            SeasonForeignId=get_season_foreign_id_model(), Team=get_team_model(), TeamForeignId=get_team_foreign_id_model())
        self.db = db
        self.dane = dane
        self.logo_root = Path(logo_root)
        self.logo_folder = logo_folder
        self.apply = apply
        self.licz = {k: _kat_licznik() for k in ('druzyny', 'zawodnicy', 'mecze')}
        self.licz_pary = {'sezon': None, 'liga': None}
        self.r = {k: [] for k in ('pominiete', 'korekty', 'do_ustalenia', 'nieobecne', 'rozbieznosci', 'dolaczono', 'brak_logo', 'zablokowane',
                                  'skroty_wyliczone', 'zmiany', 'bledy', 'kilka_aktualnych', 'tylko_dawne', 'zwolnieni')}
        self.przyn = {'jedna': 0, 'kilka': 0, 'tylko_dawne': 0, 'bez_rozroznienia': 0}           # klasyfikacja zawodników wg drużyn aktualnych (W7e-1)
        self._nast = 0
        self.scraper_id = None
        self.kadra_pary = set()
        self.zwolnieni_ids = set()                      # zawodnicy modułu zwolnieni z drużyny w tym przebiegu (nie liczą się jako „nieobecni”)
        self.fid = {}

    # -- narzędzia
    def _nowy_id(self):
        self._nast -= 1
        return self._nast

    def _dodaj(self, model, **pola):
        """Nowy rekord: w zapisie dodany i opróżniony do bazy (ma id), w podglądzie atrapa z ujemnym id."""
        if not self.apply:
            return SimpleNamespace(id=self._nowy_id(), **pola)
        obj = model(**pola)
        self.db.session.add(obj)
        self.db.session.flush()
        return obj

    def _ustaw(self, obj, **pola):
        zmienione = [k for k, v in pola.items() if getattr(obj, k) != v]
        if zmienione and self.apply:
            for k in zmienione:
                setattr(obj, k, pola[k])
        return zmienione

    def _powiaz(self, rodzaj, model, kolumna, obiekt_id, foreign):
        if self.apply:
            self.db.session.add(model(**{'scraper_id': self.scraper_id, kolumna: obiekt_id, 'foreign_id': foreign}))
            self.db.session.flush()
        self.fid[rodzaj][foreign] = obiekt_id

    def _wczytaj_powiazania(self):
        m = self.m
        self.fid = {'sezon': {}, 'liga': {}, 'druzyna': {}, 'zawodnik': {}, 'mecz': {}}
        scraper = m.Scraper.query.filter_by(folder=SCRAPER_FOLDER).first()
        if scraper is None:
            scraper = self._dodaj(m.Scraper, name=SCRAPER_NAME, folder=SCRAPER_FOLDER)
        self.scraper_id = scraper.id
        if scraper.id < 0:
            return                                           # podgląd przy pierwszym pobraniu: nic jeszcze nie jest powiązane
        for rodzaj, model, kol in (('sezon', m.SeasonForeignId, 'season_id'), ('liga', m.LeagueForeignId, 'league_id'),
                                   ('druzyna', m.TeamForeignId, 'team_id'), ('zawodnik', m.PlayerForeignId, 'player_id'),
                                   ('mecz', m.GameForeignId, 'game_id')):
            for f in model.query.filter_by(scraper_id=scraper.id):
                self.fid[rodzaj][f.foreign_id] = getattr(f, kol)

    # -- logo
    def _logo_istnieje(self, sciezka):
        rel = kanoniczna_sciezka_logo(sciezka)
        return rel.startswith(LOGO_PREFIX) and (self.logo_root / rel[len(LOGO_PREFIX):]).is_file()

    def _domyslne_logo(self):
        w_folderze = f'{LOGO_PREFIX}{self.logo_folder}/default.png'
        if self._logo_istnieje(w_folderze):
            return w_folderze, ''
        return f'{LOGO_PREFIX}default.png', ' (brak default.png w folderze modułu, użyto wspólnego)'

    def _logo(self, nazwa, bm_logo, obecne):
        """Ścieżka logo do zapisania. Zasada planu (punkt 7): brak pliku na dysku = default.png z raportem."""
        domyslne, uwaga = self._domyslne_logo()
        if bm_logo:
            kand = LOGO_PREFIX + kanoniczna_sciezka_logo(bm_logo)
            if self._logo_istnieje(kand):
                return kand
            self.r['brak_logo'].append(f'{nazwa}: brak pliku logo {bm_logo}, użyto default.png{uwaga}')
            return domyslne
        if obecne:
            kand = kanoniczna_sciezka_logo(obecne)
            if self._logo_istnieje(kand):
                return kand
            self.r['brak_logo'].append(f'{nazwa}: brak pliku logo {obecne}, użyto default.png{uwaga}')
            return domyslne
        return domyslne

    # -- sezon i liga
    def _sezon(self):
        m, d = self.m, self.dane
        wp_id, nazwa = str(d['sezon']['id']), tekst(d['sezon'].get('name'))[:100]
        obj = None
        if wp_id in self.fid['sezon']:
            obj = self.db.session.get(m.Season, self.fid['sezon'][wp_id])
        if obj is None:
            obj = m.Season.query.filter_by(name=nazwa).first()
            if obj is not None:
                self.r['dolaczono'].append(f'sezon „{nazwa}” (istniejący w module)')
                self._powiaz('sezon', m.SeasonForeignId, 'season_id', obj.id, wp_id)
        if obj is None:
            numer = (self.db.session.query(self.db.func.max(m.Season.number)).scalar() or 0) + 1
            obj = self._dodaj(m.Season, name=nazwa, number=numer)
            self._powiaz('sezon', m.SeasonForeignId, 'season_id', obj.id, wp_id)
            self.licz_pary['sezon'] = 'dodano'
            self.r['zmiany'].append(f'dodano sezon „{nazwa}”')
        else:
            zm = self._ustaw(obj, name=nazwa) if obj.name != nazwa and not m.Season.query.filter(m.Season.name == nazwa, m.Season.id != obj.id).first() else []
            self.licz_pary['sezon'] = 'zaktualizowano' if zm else 'bez_zmian'
            if zm:
                self.r['zmiany'].append(f'sezon: nazwa → „{nazwa}”')
        return obj

    def _liga(self, sezon):
        m, d = self.m, self.dane
        klucz = f'{d["liga"]["id"]}:{d["sezon"]["id"]}'
        nazwa = tekst(d['liga'].get('name'))
        if len(nazwa) > 50:
            self.r['rozbieznosci'].append(f'nazwa ligi „{nazwa}” skrócona do 50 znaków')
            nazwa = nazwa[:50]
        obj = self.db.session.get(m.League, self.fid['liga'][klucz]) if klucz in self.fid['liga'] else None
        if obj is None and sezon.id > 0:
            obj = m.League.query.filter_by(season_id=sezon.id, name=nazwa).first()
            if obj is not None:
                self.r['dolaczono'].append(f'liga „{nazwa}” (istniejąca w module)')
                self._powiaz('liga', m.LeagueForeignId, 'league_id', obj.id, klucz)
        if obj is None:
            obj = self._dodaj(m.League, season_id=sezon.id, name=nazwa, allows_draw='puchar' not in nazwa.casefold())
            self._powiaz('liga', m.LeagueForeignId, 'league_id', obj.id, klucz)
            self.licz_pary['liga'] = 'dodano'
            self.r['zmiany'].append(f'dodano ligę „{nazwa}”')
        else:
            zm = self._ustaw(obj, name=nazwa) if obj.name != nazwa and not m.League.query.filter(
                m.League.season_id == obj.season_id, m.League.name == nazwa, m.League.id != obj.id).first() else []
            self.licz_pary['liga'] = 'zaktualizowano' if zm else 'bez_zmian'
            if zm:
                self.r['zmiany'].append(f'liga: nazwa → „{nazwa}”')
        return obj

    # -- drużyny
    def _druzyny(self, liga):
        m, d = self.m, self.dane
        wp_druzyny = sorted(d['druzyny'], key=lambda t: int(t['id']))
        istniejace = {}                                          # id WP -> obiekt Team modułu (powiązany)
        for t in wp_druzyny:
            fid = self.fid['druzyna'].get(str(t['id']))
            if fid is not None:
                istniejace[int(t['id'])] = self.db.session.get(m.Team, fid)
        nazwy_zajete = {}
        for t in m.Team.query.all():
            nazwy_zajete[t.name] = t.id
        wynik = {}                                               # id WP -> obiekt Team (także atrapa)
        # skróty: ustalone w WP, istniejące w module albo do wyliczenia (unikalnie w obrębie pary)
        skroty, do_wyliczenia = {}, {}
        for t in wp_druzyny:
            wid = int(t['id'])
            meta = t.get('meta') or {}
            zwp = tekst(meta.get('bm_short_name')).upper()
            if zwp:
                if len(zwp) > 3:
                    self.r['rozbieznosci'].append(f'skrót „{zwp}” drużyny {tekst((t.get("title") or {}).get("rendered"))} obcięty do 3 znaków')
                skroty[wid] = zwp[:3]
            elif wid in istniejace and istniejace[wid] is not None and istniejace[wid].short_name:
                skroty[wid] = None                               # zostaje wartość z modułu
            else:
                do_wyliczenia[wid] = tekst((t.get('title') or {}).get('rendered'))
        zajete = [v for v in skroty.values() if v] + [istniejace[w].short_name for w, v in skroty.items() if v is None]
        for wid, (skrot, kolizja) in wylicz_unikalne(do_wyliczenia, zajete=zajete).items():
            skroty[wid] = skrot
            self.r['skroty_wyliczone'].append(f'{do_wyliczenia[wid]} → {skrot}' + (' (kolizja rozwiązana)' if kolizja else ''))
        for t in wp_druzyny:
            wid = int(t['id'])
            meta = t.get('meta') or {}
            nazwa = tekst((t.get('title') or {}).get('rendered'))[:100]
            n14 = tekst(meta.get('bm_name14'))
            obj = istniejace.get(wid)
            if obj is None:
                po_nazwie = m.Team.query.filter_by(name=nazwa).first()
                if po_nazwie is not None and po_nazwie.id not in self.fid['druzyna'].values():
                    obj = po_nazwie
                    self.r['dolaczono'].append(f'drużyna „{nazwa}” (istniejąca w module)')
                    self._powiaz('druzyna', m.TeamForeignId, 'team_id', obj.id, str(wid))
            if obj is None:
                unik, nr = nazwa, 2
                while unik in nazwy_zajete:
                    unik = f'{nazwa[:96]} ({nr})'
                    nr += 1
                if unik != nazwa:
                    self.r['rozbieznosci'].append(f'drużyna „{nazwa}” (WP {wid}): nazwa zajęta w module, zapisano jako „{unik}”')
                obj = self._dodaj(m.Team, name=unik, name_14=n14[:14] if n14 else nazwa_14(nazwa), short_name=skroty[wid],
                                  logo_path=self._logo(nazwa, meta.get('bm_logo'), ''))
                nazwy_zajete[unik] = obj.id
                self._powiaz('druzyna', m.TeamForeignId, 'team_id', obj.id, str(wid))
                self.licz['druzyny']['dodano'] += 1
                self.r['zmiany'].append(f'dodano drużynę „{unik}” ({skroty[wid]})')
            else:
                pola = {}
                if obj.name != nazwa:
                    inny = m.Team.query.filter(m.Team.name == nazwa, m.Team.id != obj.id).first()
                    if inny is None and nazwa not in {x.name for x in wynik.values() if x is not obj}:
                        pola['name'] = nazwa
                    else:
                        self.r['rozbieznosci'].append(f'drużyna „{obj.name}”: nowa nazwa w WP „{nazwa}” jest zajęta w module, zostaje stara')
                if n14:
                    pola['name_14'] = n14[:14]
                if skroty[wid]:
                    pola['short_name'] = skroty[wid]
                logo = self._logo(nazwa, meta.get('bm_logo'), obj.logo_path)
                if logo != obj.logo_path:
                    pola['logo_path'] = logo
                zm = self._ustaw(obj, **pola)
                self.licz['druzyny']['zaktualizowano' if zm else 'bez_zmian'] += 1
                if zm:
                    self.r['zmiany'].append(f'drużyna „{obj.name}”: ' + ', '.join(zm))
            wynik[wid] = obj
            # przynależność do ligi pary (grupa 1)
            if liga.id < 0 or obj.id < 0 or not m.LeagueTeam.query.filter_by(league_id=liga.id, team_id=obj.id).first():
                if self.apply:
                    self.db.session.add(m.LeagueTeam(league_id=liga.id, team_id=obj.id, group_nr=1))
                    self.db.session.flush()
        # powtórzone skróty w parze
        liczniki = {}
        for wid, o in wynik.items():
            liczniki.setdefault(skroty[wid] or o.short_name, []).append(o.name)
        for s, nazwy in sorted(liczniki.items()):
            if s and len(nazwy) > 1:
                self.r['rozbieznosci'].append(f'powtórzony skrót „{s}” w parze: ' + ', '.join(nazwy))
        return wynik

    # -- zawodnicy
    def _zawodnicy(self, druzyny):
        m, d = self.m, self.dane
        wp_ids_druzyn = set(druzyny)
        odwrot_dr = {v: k for k, v in self.fid['druzyna'].items()}          # id drużyny modułu -> id WP (tekst)
        self._stan_modulu()
        trwajace = self._mecze_trwajace()
        for z in sorted(d['zawodnicy'], key=lambda x: int(x['id'])):
            wid = int(z['id'])
            tytul = tekst((z.get('title') or {}).get('rendered'))
            aktualne_wp, dawne_wp = z.get('current_teams'), z.get('past_teams')
            rozrozniane = bool(aktualne_wp) or bool(dawne_wp)         # rekord bez obu list (stary import) ma tylko wspólną listę 'teams'
            if rozrozniane:
                # do puli pary należy zawodnik, który MA AKTUALNĄ drużynę w parze; dawne drużyny nie liczą się
                wszystkie_wp = {int(t) for t in (aktualne_wp or []) if t}
                wspolne = sorted(t for t in wszystkie_wp if t in wp_ids_druzyn)
                if not wspolne:
                    fid_z = self.fid['zawodnik'].get(str(wid))
                    obj_z = self.db.session.get(m.Player, fid_z) if fid_z is not None else None
                    self._zwolnij_z_druzyny(obj_z, tytul, wszystkie_wp, wp_ids_druzyn, odwrot_dr, trwajace, druzyny)
                    dawne_pary = sorted(int(t) for t in (dawne_wp or []) if t and int(t) in wp_ids_druzyn)
                    if dawne_pary:
                        self.przyn['tylko_dawne'] += 1
                        self.r['tylko_dawne'].append(
                            f'zawodnik {tytul}: w tej parze tylko dawne drużyny ({", ".join(druzyny[t].name for t in dawne_pary)}), '
                            f'aktualnych drużyn poza parą: {len(wszystkie_wp)}')
                    continue                                     # zawodnik innych drużyn sezonu albo tylko dawnych w parze: nie dotyczy tej pary
            else:
                wszystkie_wp = {int(t) for t in (z.get('teams') or []) if t}
                wspolne = sorted(t for t in wszystkie_wp if t in wp_ids_druzyn)
                if not wspolne:
                    continue
                self.przyn['bez_rozroznienia'] += 1
            self.kadra_pary.add(str(wid))
            fid = self.fid['zawodnik'].get(str(wid))
            obj = self.db.session.get(m.Player, fid) if fid is not None else None
            # moduł ma jedną drużynę zawodnika: zostaje obecna, jeśli WP nadal ją wymienia jako aktualną (bez przeskakiwania między parami),
            # inaczej drużyna pary o najniższym numerze WP
            biezaca = int(odwrot_dr.get(obj.team_id, -1)) if obj is not None and obj.team_id is not None else -1
            if biezaca in wszystkie_wp:
                team_id = obj.team_id
            else:
                team_id = druzyny[wspolne[0]].id
            if len(wspolne) > 1:
                self.przyn['kilka'] += 1
                wybrana = next((druzyny[t].name for t in wspolne if druzyny[t].id == team_id), None) or 'drużyna spoza pary (obecna w module)'
                self.r['kilka_aktualnych'].append(
                    f'zawodnik {tytul}: aktualne w parze: {", ".join(druzyny[t].name for t in wspolne)}; przypisano: {wybrana}'
                    + ('' if rozrozniane else ' (źródło nie rozróżnia drużyn aktualnych i dawnych)'))
            else:
                self.przyn['jedna'] += 1
            meta = z.get('meta') or {}
            nazwisko, imie = tekst(meta.get('bm_last_name')), tekst(meta.get('bm_first_name'))
            if not (nazwisko or imie):
                nazwisko, imie = podziel_nazwisko_imie(tytul)
            nr_txt = str(z.get('number') if z.get('number') is not None else '').strip()
            numer = int(nr_txt) if nr_txt.isdigit() else None
            if obj is None:
                obj = self._dodaj(m.Player, first_name=imie[:100], last_name=nazwisko[:100], number=numer, team_id=team_id)
                self._powiaz('zawodnik', m.PlayerForeignId, 'player_id', obj.id, str(wid))
                self.licz['zawodnicy']['dodano'] += 1
            else:
                zm = self._ustaw(obj, first_name=imie[:100], last_name=nazwisko[:100], number=numer, team_id=team_id)
                self.licz['zawodnicy']['zaktualizowano' if zm else 'bez_zmian'] += 1
                if zm:
                    self.r['zmiany'].append(f'zawodnik {nazwisko} {imie}: ' + ', '.join(zm))

    def _mecze_trwajace(self):
        """Mecze, w których nie wolno zmieniać drużyn: aktywne w otwartej sesji albo rozpoczęte w module i niezakończone."""
        m = self.m
        rozpoczete_niezakonczone = {r[0] for r in self.db.session.query(m.Game.id).filter(
            m.Game.id.in_(self.rozpoczete), m.Game.status != m.Game.STATUS_FINISHED)} if self.rozpoczete else set()
        return set(self.aktywne) | rozpoczete_niezakonczone

    def _zwolnij_z_druzyny(self, obj, tytul, aktualne_wp, wp_ids_druzyn, odwrot_dr, trwajace, druzyny):
        """Zawodnik modułu powiązany z WP, w parze nie ma już aktualnej drużyny: jeśli jego obecna drużyna modułu należy do pary, przechodzi do
        swojej aktualnej drużyny z WP istniejącej w module (najniższy numer WP), a gdy takiej nie ma, zostaje bez drużyny. Rekord nie jest usuwany;
        skład meczowy i zdarzenia mają własne team_id, więc historia się nie zmienia."""
        m = self.m
        if obj is None or obj.team_id is None:
            return
        biezaca_wp = odwrot_dr.get(obj.team_id)
        if biezaca_wp is None or int(biezaca_wp) not in wp_ids_druzyn:
            return
        nowa = next((self.fid['druzyna'][str(t)] for t in sorted(aktualne_wp) if str(t) in self.fid['druzyna']), None)
        nazwy = {o.id: o.name for o in druzyny.values()}
        nazwa_obecnej = nazwy.get(obj.team_id) or self.db.session.get(m.Team, obj.team_id).name
        mecze = [r[0] for r in self.db.session.query(m.GamePlayer.game_id).filter_by(player_id=obj.id)] if obj.id and obj.id > 0 else []
        if any(g in trwajace for g in mecze):
            self.r['zwolnieni'].append(f'zawodnik {tytul}: zostaje w drużynie {nazwa_obecnej} (jest w kadrze meczu, który trwa albo jest rozpoczęty w module); '
                                       f'zwolnienie przy następnym pobraniu')
            return
        zm = self._ustaw(obj, team_id=nowa)
        self.zwolnieni_ids.add(obj.id)
        cel = (nazwy.get(nowa) or self.db.session.get(m.Team, nowa).name) if nowa else 'bez drużyny'
        nierozpoczete = []
        for g in (self.db.session.query(m.Game).filter(m.Game.id.in_(mecze), m.Game.status == m.Game.STATUS_NOT_STARTED) if mecze else []):
            nierozpoczete.append(f'{g.home_team.name} – {g.away_team.name}' + (f' ({g.date:%Y-%m-%d})' if g.date else ''))
        self.r['zwolnieni'].append(f'zawodnik {tytul}: zwolniony z drużyny {nazwa_obecnej}, teraz: {cel}'
                                   + (f'; nadal w kadrze meczu nierozpoczętego: {"; ".join(nierozpoczete)}' if nierozpoczete else ''))
        if zm:
            self.licz['zawodnicy']['zaktualizowano'] += 1
            self.r['zmiany'].append(f'zawodnik {tytul}: drużyna {nazwa_obecnej} → {cel}')

    # -- mecze
    def _stan_modulu(self):
        m, db = self.m, self.db
        otwarte = [s.id for s in m.Session.query.filter(m.Session.open_slot.isnot(None))]
        self.aktywne = {r[0] for r in db.session.query(m.SessionGame.game_id).filter(
            m.SessionGame.session_id.in_(otwarte), m.SessionGame.status == 'active')} if otwarte else set()
        self.rozpoczete = ({r[0] for r in db.session.query(m.Period.game_id).distinct()}
                           | {r[0] for r in db.session.query(m.GameEvent.game_id).distinct()}
                           | {r[0] for r in db.session.query(m.GameTimer.game_id).distinct() if r[0] is not None})

    @staticmethod
    def _data(tekst_daty):
        try:
            return datetime.fromisoformat(str(tekst_daty)[:19])
        except ValueError:
            return None

    @staticmethod
    def _wynik(mecz):
        w = mecz.get('main_results') or []
        if isinstance(w, list) and len(w) >= 2 and str(w[0]).strip().lstrip('-').isdigit() and str(w[1]).strip().lstrip('-').isdigit():
            return int(w[0]), int(w[1])
        return None

    def _mecze(self, liga, druzyny):
        m, d = self.m, self.dane
        self._stan_modulu()
        puchar = 'puchar' in tekst(liga.name).casefold()
        mapa_druzyn = {wid: o for wid, o in druzyny.items()}
        nazwa_meczu = lambda g: f'{g.home_team.name if g.home_team else "?"} – {g.away_team.name if g.away_team else "?"}'
        for e in sorted(d['mecze'], key=lambda x: int(x['id'])):
            wid = int(e['id'])
            ekipy = [int(t) for t in (e.get('teams') or [])]
            tytul = tekst((e.get('title') or {}).get('rendered'))
            if len(ekipy) != 2 or 0 in ekipy:
                self.r['do_ustalenia'].append(f'{tytul} ({str(e.get("date") or "")[:10]})')
                self.licz['mecze']['pominieto'] += 1
                continue
            if ekipy[0] not in mapa_druzyn or ekipy[1] not in mapa_druzyn:
                self.r['rozbieznosci'].append(f'mecz {tytul} (WP {wid}): drużyny spoza pary, pominięty')
                self.licz['mecze']['pominieto'] += 1
                continue
            dom, gosc = mapa_druzyn[ekipy[0]], mapa_druzyn[ekipy[1]]
            wynik = self._wynik(e)
            data = self._data(e.get('date'))
            runda, znana = numer_rundy(e.get('day'))
            if not znana:
                self.r['rozbieznosci'].append(f'mecz {tytul}: nieznany tekst rundy „{tekst(str(e.get("day")))}”, ustawiono 0')
            if puchar and runda and not 1 <= runda <= 6:
                self.r['rozbieznosci'].append(f'mecz {tytul}: numer rundy {runda} poza zakresem 1-6 w pucharze, ustawiono 0')
                runda = 0
            meta = e.get('meta') or {}
            if meta.get('bm_locked') and wynik is not None:
                self.r['zablokowane'].append(f'{tytul}: wynik zablokowany w WP')
            fid = self.fid['mecz'].get(str(wid))
            g = self.db.session.get(m.Game, fid) if fid is not None else None
            if g is None:
                gole = wynik or (None, None)
                g = self._dodaj(m.Game, home_team_id=dom.id, away_team_id=gosc.id, league_id=liga.id, group_nr=1, date=data, round=runda,
                                status=m.Game.STATUS_FINISHED if wynik else m.Game.STATUS_NOT_STARTED,
                                home_team_goals=gole[0], away_team_goals=gole[1])
                self._powiaz('mecz', m.GameForeignId, 'game_id', g.id, str(wid))
                self.licz['mecze']['dodano'] += 1
                self.r['zmiany'].append(f'dodano mecz {dom.name} – {gosc.name} ({str(e.get("date") or "")[:10]})')
                continue
            nazwa = nazwa_meczu(g)
            if bool(meta.get('bm_live')) or g.id in self.aktywne or g.status == m.Game.STATUS_PENDING:
                powod = 'aktywny w sesji transmisji' if g.id in self.aktywne else 'trwa'
                self.r['pominiete'].append(f'{nazwa}: mecz {powod}, nie zmieniono')
                self.licz['mecze']['pominieto'] += 1
                continue
            if g.status != m.Game.STATUS_FINISHED and g.id in self.rozpoczete:
                self.r['pominiete'].append(f'{nazwa}: mecz rozpoczęty w module, nie zmieniono')
                self.licz['mecze']['pominieto'] += 1
                continue
            if g.status == m.Game.STATUS_FINISHED:
                self._mecz_zakonczony(g, nazwa, dom, gosc, wynik, data)
                continue
            gole = wynik or (None, None)
            zm = self._ustaw(g, home_team_id=dom.id, away_team_id=gosc.id, league_id=liga.id, date=data, round=runda,
                             status=m.Game.STATUS_FINISHED if wynik else m.Game.STATUS_NOT_STARTED,
                             home_team_goals=gole[0], away_team_goals=gole[1])
            self.licz['mecze']['zaktualizowano' if zm else 'bez_zmian'] += 1
            if zm:
                self.r['zmiany'].append(f'mecz {nazwa}: ' + ', '.join(zm))
        self._nieobecne(liga, druzyny)

    def _mecz_zakonczony(self, g, nazwa, dom, gosc, wynik, data):
        if g.home_team_id != dom.id or g.away_team_id != gosc.id:
            self.r['rozbieznosci'].append(f'{nazwa}: WP ma w zakończonym meczu inne drużyny ({dom.name} – {gosc.name}), nie zmieniono')
        if wynik is None:
            self.licz['mecze']['bez_zmian'] += 1                     # WP bez wyniku nie kasuje wyniku modułu
            return
        pola, opisy = {}, []
        if (g.home_team_goals, g.away_team_goals) != wynik:
            pola.update(home_team_goals=wynik[0], away_team_goals=wynik[1])
            opisy.append(f'korekta wyniku: moduł {g.home_team_goals}:{g.away_team_goals} → WP {wynik[0]}:{wynik[1]}')
        if data is not None and g.date != data:
            pola['date'] = data
            opisy.append(f'korekta daty: {g.date:%Y-%m-%d %H:%M} → {data:%Y-%m-%d %H:%M}' if g.date else f'data: {data:%Y-%m-%d %H:%M}')
        if pola:
            self._ustaw(g, **pola)
            self.r['korekty'].append(f'{nazwa}: ' + '; '.join(opisy))
            self.licz['mecze']['zaktualizowano'] += 1
        else:
            self.licz['mecze']['bez_zmian'] += 1

    def _nieobecne(self, liga, druzyny):
        """Rekordy modułu powiązane z WP, ale nieobecne w pobranej parze: tylko raport."""
        m, d = self.m, self.dane
        if liga.id < 0:
            return
        wp_mecze = {str(e['id']) for e in d['mecze']}
        wp_zaw = self.kadra_pary
        wp_dr = {str(t['id']) for t in d['druzyny']}
        odwrot = {k: {v: f for f, v in self.fid[k].items()} for k in ('mecz', 'zawodnik', 'druzyna')}
        for g in m.Game.query.filter_by(league_id=liga.id):
            f = odwrot['mecz'].get(g.id)
            if f is not None and f not in wp_mecze:
                self.r['nieobecne'].append(f'mecz {g.home_team.name} – {g.away_team.name} ({g.date:%Y-%m-%d})' if g.date else f'mecz {g.home_team.name} – {g.away_team.name}')
        ids_druzyn = [o.id for o in druzyny.values() if o.id > 0]
        for p in m.Player.query.filter(m.Player.team_id.in_(ids_druzyn)) if ids_druzyn else []:
            f = odwrot['zawodnik'].get(p.id)
            if f is not None and f not in wp_zaw and p.id not in self.zwolnieni_ids:
                self.r['nieobecne'].append(f'zawodnik {p.last_name} {p.first_name}')
        for lt in m.LeagueTeam.query.filter_by(league_id=liga.id):
            f = odwrot['druzyna'].get(lt.team_id)
            if f is not None and f not in wp_dr:
                self.r['nieobecne'].append(f'drużyna {lt.team.name}')

    # -- całość
    def wykonaj(self):
        if self.apply and self.db.session.get(self.m.Stadium, 1) is None:
            raise RuntimeError('brak domyślnego stadionu (id 1) w bazie modułu')
        self._wczytaj_powiazania()
        sezon = self._sezon()
        liga = self._liga(sezon)
        druzyny = self._druzyny(liga)
        self._zawodnicy(druzyny)
        self._mecze(liga, druzyny)
        return self.raport()

    def zmieniono(self):
        return (any(self.licz[k][c] for k in self.licz for c in ('dodano', 'zaktualizowano'))
                or self.licz_pary['sezon'] in ('dodano', 'zaktualizowano') or self.licz_pary['liga'] in ('dodano', 'zaktualizowano')
                or bool(self.r['dolaczono']))

    def raport(self):
        def ucieta(lista):
            return lista[:LIMIT_LISTY] + ([f'… i {len(lista) - LIMIT_LISTY} kolejnych'] if len(lista) > LIMIT_LISTY else [])
        return {'liczniki': self.licz, 'przynaleznosc': self.przyn, 'sezon': self.licz_pary['sezon'], 'liga': self.licz_pary['liga'],
                'zmieniono': self.zmieniono(), 'do_ustalenia_liczba': len(self.r['do_ustalenia']),
                **{k: ucieta(v) for k, v in self.r.items()}}


def kopia_bazy(db, kopie_dir):
    """Kopia pliku bazy SQLite przed zapisem (API kopii SQLite, bezpieczna przy otwartej bazie); zostaje ostatnie 5. Zwraca ścieżkę albo None."""
    sciezka = db.engine.url.database
    if not sciezka or sciezka == ':memory:' or not os.path.isfile(sciezka):
        return None
    os.makedirs(kopie_dir, exist_ok=True)
    cel = Path(kopie_dir) / f'{Path(sciezka).stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db'
    src, dst = sqlite3.connect(sciezka), sqlite3.connect(str(cel))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for stara in sorted(Path(kopie_dir).glob(f'{Path(sciezka).stem}-*.db'))[:-KOPII_ZACHOWANYCH]:
        try:
            stara.unlink()
        except OSError:
            pass
    return str(cel)


def pobierz_pare(client, db, league_id, season_id, logo_root, logo_folder, kopie_dir, apply):
    """Podgląd (apply=False) albo zapis jednej pary. Zwraca {'ok': bool, 'zapisano': bool, 'raport': {...}, 'blad': str}. Nie zgłasza wyjątków."""
    if not _lock.acquire(blocking=False):
        return {'ok': False, 'zapisano': False, 'blad': 'Pobieranie z WP już trwa'}
    try:
        try:
            dane = pobierz_dane_pary(client, league_id, season_id)
        except WpError as e:
            return {'ok': False, 'zapisano': False, 'blad': f'Pobieranie przerwane, baza bez zmian: {e}'}
        try:
            db.session.rollback()
            podglad = Pobieranie(db, dane, logo_root, logo_folder, apply=False).wykonaj()
            db.session.rollback()
            if not apply or not podglad['zmieniono']:
                return {'ok': True, 'zapisano': False, 'raport': podglad, 'pobrano': dane['pobrano']}
            kopia = kopia_bazy(db, kopie_dir)
            try:
                raport = Pobieranie(db, dane, logo_root, logo_folder, apply=True).wykonaj()
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            raport['kopia'] = kopia
            return {'ok': True, 'zapisano': True, 'raport': raport, 'pobrano': dane['pobrano']}
        except Exception as e:
            db.session.rollback()
            return {'ok': False, 'zapisano': False, 'blad': f'Pobieranie przerwane, baza bez zmian: {type(e).__name__}: {e}'}
    finally:
        _lock.release()

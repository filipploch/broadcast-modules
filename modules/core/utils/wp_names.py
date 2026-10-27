"""Nazwy z WP w postaci wymaganej przez moduł (W7a): skrót 3-znakowy, nazwa 14-znakowa, imię i nazwisko zawodnika, numer kolejki.

Algorytm skrótu jest kopią tools/import_wp/skroty.py (te same przypadki testowe w obu miejscach): skrót wyliczony w narzędziu importu
i w module ma być taki sam. Skróty ustawione w WP (bm_short_name) przenosimy bez zmian, wyliczenie dotyczy tylko ich braku."""
import html
import re
import unicodedata

FORMY_PRAWNE = {'KS', 'LKS', 'MKS', 'BKS', 'AP', 'UKS', 'OKS', 'GKS', 'GLKS', 'MLKS', 'KP', 'FC', 'AKS', 'SKS', 'RKS', 'KKS', 'ZKS', 'TS', 'LZS', 'LKP', 'SK'}

# tekst rundy pucharowej w WP (pole "day") -> numer rundy modułu (round_name: 1/16 finału … Finał)
RUNDY_PUCHAROWE = {'1/16 finału': 1, '1/8 finału': 2, '1/4 finału': 3, 'ćwierćfinał': 3, 'półfinał': 4, 'mecz o 3. miejsce': 5, 'mecz o 3 miejsce': 5,
                   'mecz o trzecie miejsce': 5, 'finał': 6}


def tekst(wartosc):
    """Tekst z WP bez encji HTML i z pojedynczymi spacjami."""
    return ' '.join(html.unescape(wartosc or '').split())


def _ascii_wielkie(t):
    t = unicodedata.normalize('NFKD', t).replace('ł', 'l').replace('Ł', 'L')
    return re.sub(r'[^A-Z0-9]', '', ''.join(c for c in t if not unicodedata.combining(c)).upper())


def slowa_rdzenia(nazwa):
    """Słowa nazwy bez formy prawnej na początku (zostaje co najmniej jedno słowo)."""
    slowa = [w for w in re.split(r'\s+', (nazwa or '').strip()) if _ascii_wielkie(w)]
    i = 0
    while i < len(slowa) - 1 and _ascii_wielkie(slowa[i]) in FORMY_PRAWNE:
        i += 1
    return slowa[i:]


def wylicz_skrot(nazwa):
    slowa = slowa_rdzenia(nazwa)
    if not slowa:
        return ''
    kandydat = _ascii_wielkie(slowa[0])[:3]
    for w in slowa[1:]:
        if len(kandydat) >= 3:
            break
        kandydat += _ascii_wielkie(w)[:1]
    return kandydat


def wylicz_unikalne(nazwy, zajete=()):
    """nazwy: {klucz: nazwa}; zajete: skróty już przydzielone. Zwraca {klucz: (skrót, kolizja_rozwiazana)}."""
    uzyte = set(zajete)
    wynik = {}
    for klucz in sorted(nazwy, key=lambda k: (nazwy[k] or '').casefold()):
        kandydat = wylicz_skrot(nazwy[klucz])
        kolizja = kandydat in uzyte
        if kolizja:
            proby = []
            for w in slowa_rdzenia(nazwy[klucz])[1:]:
                z = _ascii_wielkie(w)
                if z:
                    proby.append(kandydat[:2] + z[0])
            proby += [kandydat[:2] + c for c in '23456789']
            kandydat = next((p for p in proby if p not in uzyte), kandydat)
        uzyte.add(kandydat)
        wynik[klucz] = (kandydat, kolizja)
    return wynik


def nazwa_14(nazwa):
    """Nazwa do 14 znaków: cała, jeśli się mieści, inaczej kolejne słowa do granicy 14 znaków (pierwsze słowo dłuższe: obcięte)."""
    nazwa = tekst(nazwa)
    if len(nazwa) <= 14:
        return nazwa
    wynik = ''
    for slowo in nazwa.split(' '):
        proba = f'{wynik} {slowo}'.strip()
        if len(proba) > 14:
            break
        wynik = proba
    return wynik or nazwa[:14]


def podziel_nazwisko_imie(tytul):
    """„Nazwisko Imię” -> (nazwisko, imię). Dwa wyrazy: pewny podział; jeden wyraz: samo nazwisko; więcej: ostatni wyraz to imię."""
    t = tekst(tytul).split()
    if len(t) == 1:
        return t[0], ''
    if not t:
        return '', ''
    return ' '.join(t[:-1]), t[-1]


def numer_rundy(day):
    """Pole "day" meczu w WP -> (numer rundy, czy_rozpoznano). Cyfry: liczba; tekst pucharowy: 1-6; puste: 0; nieznany tekst: 0 i False."""
    t = tekst(str(day if day is not None else ''))
    if not t:
        return 0, True
    cyfry = re.search(r'\d+', t)
    if t.isdigit():
        return int(t), True
    if t.casefold() in RUNDY_PUCHAROWE:
        return RUNDY_PUCHAROWE[t.casefold()], True
    if cyfry and re.fullmatch(r'(?:kolejka|runda|k\.?)\s*\d+\.?', t, re.I):
        return int(cyfry.group()), True
    return 0, False

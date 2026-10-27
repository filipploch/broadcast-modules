"""Skrót 3-znakowy drużyny (Team.short_name modułu) z nazwy: wartość WYLICZONA, gdy nie ma jej w API ani w starej bazie (W7-0b).

Reguła: z początku nazwy pomijamy formę prawną klubu (KS, LKS, MKS, BKS, AP, UKS…), bierzemy trzy pierwsze litery pierwszego z pozostałych słów,
wielkimi literami i BEZ polskich znaków (Ł→L, Ó→O); gdy pierwsze słowo ma mniej niż 3 znaki, dopełniamy pierwszymi literami kolejnych słów („NO NAME” -> NON, „16 Batalion” -> 16B); nazwa z jednego krótkiego słowa zostaje sama („K2”). Kolizje w obrębie zbioru drużyn
rozwiązujemy podmianą trzeciego znaku na pierwszą literę kolejnego słowa nazwy, a dalej cyfrą 2-9. Ta sama reguła i te same przypadki testowe
są w module (W7a), żeby skrót wyliczony w narzędziu i w module był taki sam."""
import re
import unicodedata

FORMY_PRAWNE = {'KS', 'LKS', 'MKS', 'BKS', 'AP', 'UKS', 'OKS', 'GKS', 'GLKS', 'MLKS', 'KP', 'FC', 'AKS', 'SKS', 'RKS', 'KKS', 'ZKS', 'TS', 'LZS', 'LKP', 'SK'}


def _ascii_wielkie(tekst):
    t = unicodedata.normalize('NFKD', tekst).replace('ł', 'l').replace('Ł', 'L')
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
    for w in slowa[1:]:                                  # pierwsze słowo krótsze niż 3 znaki: dopełniamy pierwszymi literami kolejnych słów („NO NAME” -> NON)
        if len(kandydat) >= 3:
            break
        kandydat += _ascii_wielkie(w)[:1]
    return kandydat


def wylicz_unikalne(nazwy, zajete=()):
    """nazwy: {klucz: nazwa}; zajete: skróty już przydzielone (stałe). Zwraca {klucz: (skrót, kolizja_rozwiazana: bool)} dla wszystkich kluczy."""
    uzyte = set(zajete)
    wynik = {}
    for klucz in sorted(nazwy, key=lambda k: (nazwy[k] or '').casefold()):
        kandydat = wylicz_skrot(nazwy[klucz])
        kolizja = kandydat in uzyte
        if kolizja:
            slowa = slowa_rdzenia(nazwy[klucz])
            proby = []
            for w in slowa[1:]:
                z = _ascii_wielkie(w)
                if z:
                    proby.append(kandydat[:2] + z[0])
            proby += [kandydat[:2] + c for c in '23456789']
            kandydat = next((p for p in proby if p not in uzyte), kandydat)
        uzyte.add(kandydat)
        wynik[klucz] = (kandydat, kolizja)
    return wynik

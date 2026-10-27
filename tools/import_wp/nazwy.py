"""Podział nazwy zawodnika na nazwisko i imię (WP trzyma jedno pole tytułu „Nazwisko Imię”)."""
import html


def oczyść(tekst):
    return ' '.join(html.unescape(tekst or '').split())


def podziel_nazwisko_imie(tytul):
    """„Nazwisko Imię” -> (nazwisko, imię, pewne). Dwa wyrazy: pewne. Jeden albo więcej niż dwa (nazwisko wieloczłonowe, drugie imię):
    ostatni wyraz traktowany jako imię, wynik oznaczony jako niepewny do ręcznego sprawdzenia w WP."""
    t = oczyść(tytul).split()
    if len(t) == 2:
        return t[0], t[1], True
    if len(t) == 1:
        return t[0], '', False
    if not t:
        return '', '', False
    return ' '.join(t[:-1]), t[-1], False

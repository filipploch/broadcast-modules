"""Wspolne narzedzia testow modulow (E1): aplikacja w trybie 'testing' na tymczasowej bazie SQLite.

Jeden proces = jeden modul (oba moduly maja pakiet 'app'). Uruchamianie: python tests/modules/run.py [futsal_nalf|garbarnia]
"""
import os, sys, tempfile, pathlib, shutil

REPO = pathlib.Path(__file__).resolve().parents[2]
MODULES = REPO / "modules"


def boot(module):
    """Zwraca (app, tmpdir). Wolac raz na proces, przed importem czegokolwiek z modulu."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bm-test-"))
    os.environ["BM_TEST_DATABASE_URL"] = "sqlite:///" + (tmp / "test.db").as_posix()
    sys.path[:0] = [str(MODULES / module), str(MODULES)]
    os.chdir(MODULES / module)
    from app import create_app
    from core.extensions import db
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    return app, tmp


def reset_db(app):
    """Czysta baza przed kazdym testem."""
    from core.extensions import db
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()


def seed(app):
    """Dwa sezony (starszy z meczami, nowszy bez), dwie ligi, trzy druzyny, dwa mecze starszego sezonu. Zwraca slownik id."""
    from core.extensions import db
    from app.models import Season, League, Team, LeagueTeam, Game, Stadium
    with app.app_context():
        s1 = Season(number=30, name="Jesien 2025"); db.session.add(s1); db.session.flush()
        lg = League(season_id=s1.id, name="Dywizja A", allows_draw=True); db.session.add(lg); db.session.flush()
        teams = [Team(name=n, name_14=n, short_name=n[:3].upper()) for n in ("Alfa", "Beta", "Gamma")]
        db.session.add_all(teams); db.session.flush()
        db.session.add_all([LeagueTeam(league_id=lg.id, team_id=t.id, group_nr=1) for t in teams])
        st = Stadium(name="Hala", address="ul. Testowa 1", city="Krakow"); db.session.add(st); db.session.flush()
        g1 = Game(home_team_id=teams[0].id, away_team_id=teams[1].id, league_id=lg.id, group_nr=1, stadium_id=st.id,
                  status=Game.STATUS_NOT_STARTED, round=1)
        g2 = Game(home_team_id=teams[1].id, away_team_id=teams[2].id, league_id=lg.id, group_nr=1, stadium_id=st.id,
                  status=Game.STATUS_NOT_STARTED, round=2)
        db.session.add_all([g1, g2]); db.session.commit()
        return {"season": s1.id, "league": lg.id, "g1": g1.id, "g2": g2.id, "teams": [t.id for t in teams]}


def settings(app):
    from core.models.base_settings import get_settings_model
    return get_settings_model().get_settings()

# Helper App — szkielet

Apka "pomocnika realizatora", docelowo hostowana na Render, zgodna z
kontraktem opisanym w `docs/helper-app-design.md` (repo modułu głównego).

## Co tu jest (ten branch)

- Flask app factory (`app/__init__.py`) + SQLAlchemy + Flask-Login.
- Jeden model `User` (`app/models.py`) z rolą `admin` / `helper`,
  hasłem hashowanym (`werkzeug.security`), flagą `active` (miękkie
  wyłączenie konta zamiast kasowania).
- Logowanie (`/login`) wspólne dla obu ról, przekierowanie po roli:
  `admin` → `/admin`, `helper` → `/panel`.
- Panel admina (`/admin`): lista pomocników, dodawanie nowego
  (generuje tymczasowe hasło), włączanie/wyłączanie konta.
- Panel pomocnika (`/panel`): **statyczny szkic UI** — formularz
  zgłoszenia zdarzenia (typ, drużyna, komentarz) z mockowanymi opcjami.
- `flask create-admin` — interaktywne tworzenie kolejnego admina lokalnie.
- Auto-bootstrap pierwszego admina z `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  przy starcie (wygodne na Render Hobby bez łatwego dostępu do shella).

## Czego tu NIE ma (świadomie, na razie)

- **Żadnego realnego połączenia z modułem głównym.** `HelperRelayClient`
  po stronie modułu głównego już istnieje i czeka na WSS z tokenem
  (`HELPER_RELAY_TOKEN`) — tu jeszcze nic się do niego nie łączy. Formularz
  zgłoszenia (`/panel/submit`) tylko pokazuje komunikat "nie wysłano".
- Push live danych (lista meczów, timeline już zalogowanych zdarzeń,
  sygnały start/koniec okresu) — panel pomocnika pokazuje dziś tylko
  zaszyte na sztywno (mock) typy zdarzeń i drużyny "Gospodarze/Goście".
- Migracje schematu (Alembic/Flask-Migrate) — tabele powstają przez
  `db.create_all()` przy starcie (idempotentne, nic nie kasuje/zmienia
  istniejących kolumn). Jeśli schemat zacznie się realnie zmieniać w
  produkcji, warto dodać Flask-Migrate.
- Zmiana hasła przy pierwszym logowaniu, reset hasła, self-service dla
  pomocników — dziś hasło tymczasowe pokazuje się adminowi raz przy
  tworzeniu konta.

## Uruchomienie lokalnie

```bash
cd helper-app
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # i uzupełnij wartości
flask create-admin               # albo ustaw ADMIN_USERNAME/ADMIN_PASSWORD w .env
python run.py                    # http://localhost:5001
```

Bez `ADMIN_USERNAME`/`ADMIN_PASSWORD` w `.env` i bez `flask create-admin`
nie będzie żadnego konta — `/login` zawsze odrzuci próbę logowania.

## Deploy na Render

- Root Directory: `helper-app` (albo użyj `render.yaml` — "New > Blueprint").
- Baza: managed PostgreSQL Render, `DATABASE_URL` wstrzykiwany automatycznie
  przez Render przy użyciu `render.yaml` (`fromDatabase`).
- Start command: `gunicorn run:app`.
- Ustaw `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` jako zmienne
  środowiskowe serwisu (w `render.yaml` są oznaczone `sync: false` —
  Render poprosi o wartość ręcznie przy pierwszym deployu).

## Następne kroki (poza zakresem tego szkieletu)

Patrz `docs/helper-app-design.md` sekcja 9 w repo modułu głównego —
w szczególności: klient WSS łączący się do modułu głównego
(`HELPER_RELAY_TOKEN`), realny push danych meczu do panelu pomocnika,
obsługa korekt istniejących zdarzeń, `kind='substitution'`.

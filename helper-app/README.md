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
- Panel pomocnika (`/panel`): link do realnej funkcji "Ustaw skład meczowy"
  + **wciąż statyczny szkic UI** zgłoszenia zdarzenia (typ, drużyna,
  komentarz) z mockowanymi opcjami.
- **Skład meczowy (`/panel/squad`, garbarnia)** — pierwsza w pełni działająca
  funkcja, koniec do końca z modułem głównym. Moduł główny wysyła
  (`POST /api/relay/squad`) kadrę drużyny (+ aktualnego trenera); pomocnik
  przypisuje graczy do wyjściowej jedenastki/rezerwy i edytuje trenera;
  "Wyślij do modułu głównego" pakuje to w propozycję, którą moduł główny
  odbiera przez (`GET /api/relay/squad/proposals`) i operator zatwierdza
  albo odrzuca po stronie modułu głównego. Modele: `SquadPush`,
  `SquadPushPlayer` (`app/models.py`); transport: `app/routes/relay.py`
  (token `HELPER_APP_REST_TOKEN`, **nie** `HELPER_RELAY_TOKEN` — patrz niżej).
- `flask create-admin` — interaktywne tworzenie kolejnego admina lokalnie.
- Auto-bootstrap pierwszego admina z `ADMIN_USERNAME`/`ADMIN_PASSWORD`
  przy starcie (wygodne na Render Hobby bez łatwego dostępu do shella).

## Czego tu NIE ma (świadomie, na razie)

- **Żadnego WSS połączenia z modułem głównym.** `HelperRelayClient` po
  stronie modułu głównego istnieje i czeka na WSS z tokenem
  (`HELPER_RELAY_TOKEN`) — to wciąż niepodłączone i zarezerwowane pod
  przyszły *live* strumień zdarzeń (gole, faule na bieżąco). Funkcja
  "Skład meczowy" powyżej **nie czeka na to** — dostała własny, osobny,
  lekki kanał REST (`app/routes/relay.py`, token `HELPER_APP_REST_TOKEN`),
  bo z natury jest request/response, nie live stream. Formularz zgłoszenia
  zdarzenia (`/panel/submit`) nadal tylko pokazuje komunikat "nie wysłano".
- Push live danych do panelu zgłoszeń zdarzeń (lista meczów, timeline już
  zalogowanych zdarzeń, sygnały start/koniec okresu) — to wciąż mock.
- Migracje schematu (Alembic/Flask-Migrate) — tabele powstają przez
  `db.create_all()` przy starcie (idempotentne, nic nie kasuje/zmienia
  istniejących kolumn). Jeśli schemat zacznie się realnie zmieniać w
  produkcji, warto dodać Flask-Migrate.
- Zmiana hasła przy pierwszym logowaniu, reset hasła, self-service dla
  pomocników — dziś hasło tymczasowe pokazuje się adminowi raz przy
  tworzeniu konta.
- Scoping pomocnik→drużyna — każdy zalogowany pomocnik widzi wszystkie
  otwarte propozycje składu, niezależnie od meczu/drużyny.

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
- Ustaw `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
  `HELPER_APP_REST_TOKEN` jako zmienne środowiskowe serwisu (w `render.yaml`
  są oznaczone `sync: false` — Render poprosi o wartość ręcznie przy
  pierwszym deployu). `HELPER_APP_REST_TOKEN` musi być identyczny z
  `HELPER_APP_REST_TOKEN` w konfiguracji modułu głównego (`config.py`).

## Następne kroki (poza zakresem tego szkieletu)

Patrz `docs/helper-app-design.md` sekcja 9 w repo modułu głównego —
w szczególności: klient WSS łączący się do modułu głównego
(`HELPER_RELAY_TOKEN`), realny push danych meczu do panelu pomocnika,
obsługa korekt istniejących zdarzeń, `kind='substitution'`.

# Mózg Hermesa

Wizualizacja „mózgu” agentów [Hermes](https://github.com/NousResearch) na żywo: każde zapytanie, myślenie modelu, użycie narzędzia, skilla, pamięci czy notatki z Obsidiana zapala ścieżkę w sieci neuronów. Obok czat z agentem i panel zadań.

![Zrzut ekranu (dane demo)](docs/screenshot.png)

*Zrzut z trybu demo — wszystkie dane są zmyślone.*

## Funkcje

- **Sieć neuronów** — kanały (Telegram, Discord, CLI, cron, API) → gateway → agenci → modele, narzędzia, skille, pamięć, vault Obsidiana, usługi zewnętrzne.
- **Na żywo** — serwer czyta (tylko do odczytu) bazy `state.db` Hermesa i strumieniuje zdarzenia przez SSE; ścieżki się podświetlają, a często używane trasy „wydeptują się” (30 dni historii).
- **Radar agentów** — kto był aktywny i kiedy.
- **Podgląd kodu** — co agenci ostatnio pisali (`write_file`, `patch`, `terminal`, `execute_code`).
- **Panel boczny** (opcjonalny backend) — czat, zadania, harmonogram, zakupy, spotkania.
- **Prywatność** — wybrane foldery vaulta pokazywane bez tytułów notatek; serwer domyślnie słucha tylko na `127.0.0.1`.
- **Okno natywne** (`okno/`, Rust + WebKitGTK) — opcjonalne okno bez belki z ikoną i wpisem w menu.
- **Tryb demo** — zmyślone notatki, sesje i skille w `demo/`, żeby zobaczyć działanie bez własnego Hermesa.

## Wymagania

- Python 3.9+ (tylko biblioteka standardowa)
- przeglądarka
- opcjonalnie: Hermes (`~/.hermes`) i vault Obsidiana
- opcjonalnie dla okna: Rust, GTK 3, WebKitGTK 4.1 (`libwebkit2gtk-4.1-dev`)

## Uruchomienie

```bash
# demo (zmyślone dane, nic nie musisz mieć)
python3 server/server.py --demo        # albo: MOZG_DEMO=1 python3 server/server.py
# → http://127.0.0.1:8110/

# z własnym Hermesem
cp config.example.json ~/.config/mozg-hermesa/config.json   # i dostosuj
python3 server/server.py
```

Okno natywne (opcjonalnie):

```bash
cd okno && cargo build --release
MOZG_ADRES=http://127.0.0.1:8110 ./target/release/mozg-okno
./target/release/mozg-okno --instaluj   # ikona + wpis w menu
```

## Konfiguracja

Kolejność: zmienne środowiskowe > plik konfiguracyjny > domyślne. Plik: `$MOZG_CONFIG` lub `~/.config/mozg-hermesa/config.json` (wzór: `config.example.json`).

| Klucz / zmienna | Domyślnie | Opis |
|---|---|---|
| `hermes_home` / `MOZG_HERMES_HOME` | `~/.hermes` | katalog Hermesa (state.db, skills, memories, profiles) |
| `vault` / `MOZG_VAULT` | `~/Obsidian/Vault` | vault Obsidiana |
| `host` / `MOZG_HOST` | `127.0.0.1` | adres nasłuchu |
| `port` / `MOZG_PORT` | `8110` | port |
| `backend` / `MOZG_BACKEND` | puste | opcjonalny backend czatu/zadań (`host:port`); puste = czat i listy wyłączone |
| `agents` | auto | profil → nazwa wyświetlana (`""` = profil główny) |
| `private_folders` | `[]` | foldery vaulta bez tytułów notatek |
| `services`, `hosts` | przykłady | węzły usług/maszyn wykrywane regexem w poleceniach terminala |
| `MOZG_DEMO=1` / `--demo` | — | tryb demo |
| `MOZG_ADRES` (okno) | `http://127.0.0.1:8110` | adres serwera dla okna natywnego |

Serwer otwiera bazy Hermesa wyłącznie w trybie tylko-do-odczytu. Nie wystawiaj go do internetu — nie ma uwierzytelniania.

## Zastrzeżenia

Prywatny projekt hobbystyczny, tworzony do nauki i własnego użytku. Nie jest powiązany z Anthropic. Oprogramowanie udostępniane „tak jak jest”, bez gwarancji.

Licencja: [MIT](LICENSE) © longer54

---

# Hermes Brain (English)

A live visualisation of the "brain" of [Hermes](https://github.com/NousResearch) agents: every request, model call, tool, skill, memory lookup or Obsidian note lights up a path in a neural-style graph. With a side chat and a task panel.

![Screenshot (demo data)](docs/screenshot.png)

*Screenshot taken in demo mode — all data is fictional. The UI is in Polish.*

## Features

- **Neuron graph** — channels (Telegram, Discord, CLI, cron, API) → gateway → agents → models, tools, skills, memory, Obsidian vault, external services.
- **Live** — the server reads Hermes `state.db` files (read-only) and streams events over SSE; frequently used routes become "worn paths" (30 days of history).
- **Agent radar** — who was active and when.
- **Code view** — what the agents recently wrote (`write_file`, `patch`, `terminal`, `execute_code`).
- **Side panel** (optional backend) — chat, tasks, schedule, shopping list, meetings.
- **Privacy** — selected vault folders are shown without note titles; the server binds to `127.0.0.1` by default.
- **Native window** (`okno/`, Rust + WebKitGTK) — optional frameless window with icon and menu entry.
- **Demo mode** — fictional notes, sessions and skills in `demo/` so you can try it without your own Hermes.

## Requirements

- Python 3.9+ (standard library only), a browser
- optional: Hermes (`~/.hermes`) and an Obsidian vault
- optional for the window: Rust, GTK 3, WebKitGTK 4.1

## Running

```bash
python3 server/server.py --demo        # or MOZG_DEMO=1; open http://127.0.0.1:8110/
cp config.example.json ~/.config/mozg-hermesa/config.json && python3 server/server.py
cd okno && cargo build --release && MOZG_ADRES=http://127.0.0.1:8110 ./target/release/mozg-okno
```

## Configuration

Environment variables > config file (`$MOZG_CONFIG` or `~/.config/mozg-hermesa/config.json`) > defaults. See the table above: `MOZG_HERMES_HOME` (default `~/.hermes`), `MOZG_VAULT` (`~/Obsidian/Vault`), `MOZG_HOST` (`127.0.0.1`), `MOZG_PORT` (`8110`), `MOZG_BACKEND` (optional), `MOZG_DEMO`, and `MOZG_ADRES` for the window. There is no authentication — do not expose it to the internet.

## Disclaimer

A private hobby project, made for learning and personal use. Not affiliated with Anthropic. The software is provided "as is", without warranty of any kind.

License: [MIT](LICENSE) © longer54

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional
import math

DEFAULT_DB = Path(__file__).parent / "database.db"
DEFAULT_OUT = Path(__file__).parent / "output"


def get_games_with_events(conn):
    sql = "SELECT g.id AS game_id, ht.short_name AS home_short, at.short_name AS away_short, g.date AS date FROM games g JOIN teams ht ON ht.id = g.home_team_id JOIN teams at ON at.id = g.away_team_id WHERE EXISTS (SELECT 1 FROM game_events ge WHERE ge.game_id = g.id) ORDER BY g.date DESC"
    conn.row_factory = sqlite3.Row
    return conn.execute(sql).fetchall()


def get_game_by_id(conn, game_id):
    sql = "SELECT g.id AS game_id, ht.short_name AS home_short, at.short_name AS away_short, g.date AS date FROM games g JOIN teams ht ON ht.id = g.home_team_id JOIN teams at ON at.id = g.away_team_id WHERE g.id = ?"
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, (game_id,)).fetchone()


def get_game_events(conn, game_id):
    sql = "SELECT ge.video_path AS video_path, ge.replay_start_time AS replay_start_time, ge.replay_end_time AS replay_end_time, e.short_name AS event_short_name FROM game_events ge JOIN events e ON e.id = ge.event_id WHERE ge.game_id = ? AND ge.video_path IS NOT NULL AND ge.replay_start_time IS NOT NULL AND ge.replay_end_time IS NOT NULL ORDER BY ge.replay_start_time ASC"
    return conn.execute(sql, (game_id,)).fetchall()


def get_event_cameras(conn, game_id):
    sql = "SELECT ec.video_path AS video_path, ec.replay_start_time AS replay_start_time, ec.replay_end_time AS replay_end_time, e.short_name AS event_short_name FROM event_cameras ec JOIN game_events ge ON ge.id = ec.game_event_id JOIN events e ON e.id = ge.event_id WHERE ge.game_id = ? AND ec.video_path IS NOT NULL ORDER BY ec.replay_start_time ASC"
    return conn.execute(sql, (game_id,)).fetchall()


def safe_name(text):
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
    return "".join(c if c in keep else "_" for c in text)


def make_folder(base, date, home, away):
    date_part = (date or "no-date")[:10]
    name = safe_name("{}_{}x{}".format(date_part, home, away))
    folder = base / name
    if not folder.exists():
        folder.mkdir(parents=True)
    return folder


def csv_filename(video_path):
    return Path(video_path).name + ".csv"


def save_csv(folder, filename, rows):
    path = folder / filename
    fields = ["replay_start_time", "replay_end_time", "event_short_name"]
    with open(str(path), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writerows(rows)
    return path


def group_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["video_path"]].append({
            "replay_start_time": math.ceil(row["replay_start_time"] / 1000.0),
            "replay_end_time": math.ceil(row["replay_end_time"] / 1000.0),
            "event_short_name": row["event_short_name"],
        })
    for k in groups:
        groups[k].sort(key=lambda r: r["replay_start_time"])
    return groups


def export_game(conn, game, output_dir):
    game_id = game["game_id"]
    home = game["home_short"]
    away = game["away_short"]
    date = game["date"]

    folder = make_folder(output_dir, date, home, away)
    print("")
    print("[DIR] " + str(folder))

    saved = 0

    ge_rows = get_game_events(conn, game_id)
    if ge_rows:
        groups = group_rows(ge_rows)
        print("")
        print("  game_events: " + str(len(ge_rows)) + " rows, " + str(len(groups)) + " file(s)")
        for vpath, rows in groups.items():
            fname = csv_filename(vpath)
            save_csv(folder, fname, rows)
            print("  [OK] " + fname + " (" + str(len(rows)) + " rows)")
            saved += 1
    else:
        print("")
        print("  game_events: no rows with video_path and replay times")

    ec_rows = get_event_cameras(conn, game_id)
    if ec_rows:
        groups = group_rows(ec_rows)
        print("")
        print("  event_cameras: " + str(len(ec_rows)) + " rows, " + str(len(groups)) + " file(s)")
        for vpath, rows in groups.items():
            fname = csv_filename(vpath)
            save_csv(folder, fname, rows)
            print("  [OK] " + fname + " (" + str(len(rows)) + " rows)")
            saved += 1
    else:
        print("")
        print("  event_cameras: no records for this game")

    print("")
    if saved:
        print("  Done. " + str(saved) + " CSV file(s) saved.")
    else:
        print("  [!] No files saved -- no replay data found.")


def pick_game(conn):
    games = get_games_with_events(conn)
    if not games:
        print("No games with recorded events found.")
        return None

    print("")
    print("Games with recorded events:")
    print("")
    for g in games:
        date_str = (g["date"] or "no date")[:16]
        line = "  " + str(g["game_id"]).rjust(4) + "  " + g["home_short"] + " x " + g["away_short"] + "  " + date_str
        print(line)

    print("")
    while True:
        raw = str(input("Enter game_id (or q to quit): ")).strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        if not raw.isdigit():
            print("  Please enter an integer.")
            continue
        gid = int(raw)
        game = get_game_by_id(conn, gid)
        if game is None:
            print("  Game id=" + str(gid) + " not found. Try again.")
            continue
        return game


def run(db_path, output_dir, game_id=None):
    if not db_path.exists():
        print("[ERR] Database file not found: " + str(db_path))
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        if game_id is not None:
            game = get_game_by_id(conn, game_id)
            if game is None:
                print("[ERR] Game id=" + str(game_id) + " not found.")
                sys.exit(1)
            export_game(conn, game, output_dir)
        else:
            game = pick_game(conn)
            if game is None:
                print("Cancelled.")
                return
            export_game(conn, game, output_dir)

        conn.close()

    except sqlite3.OperationalError as e:
        print("[ERR] Database error: " + str(e))
        print("      Make sure database.db is fully initialised.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Export replay data to CSV files.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to database.db")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output folder")
    parser.add_argument("--game-id", type=int, default=None, dest="game_id", help="Export this game directly")
    args = parser.parse_args()
    run(db_path=args.db, output_dir=args.output, game_id=args.game_id)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A tiny, local-first work log web app. Uses only the Python standard library."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import sys
import threading
import webbrowser
from contextlib import contextmanager
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from reports import build_annual_report


ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
APP_DATA_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
DB_PATH = Path(os.environ.get("WORKLOG_DB", APP_DATA_DIR / "data" / "worklog.sqlite3"))
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
MAX_BODY = 64 * 1024


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


@contextmanager
def db_session():
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize() -> None:
    with db_session() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date TEXT NOT NULL,
                project_number TEXT NOT NULL,
                project_name TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                hours REAL NOT NULL CHECK (hours > 0 AND hours <= 24),
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS entries_work_date ON entries(work_date)")


def valid_date(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Date is required.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Enter a valid date.") from exc


def clean_text(value: object, label: str, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        value = ""
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} is required.")
    if len(value) > limit:
        raise ValueError(f"{label} must be {limit} characters or fewer.")
    return value


def parse_entry(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Expected a work record.")
    try:
        hours = float(payload.get("hours", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("Hours must be a number between 0.25 and 24.") from exc
    if not 0.25 <= hours <= 24:
        raise ValueError("Hours must be between 0.25 and 24.")
    hours = round(hours * 4) / 4
    return {
        "work_date": valid_date(payload.get("work_date")),
        "project_number": clean_text(payload.get("project_number"), "Project number", 80, True),
        "project_name": clean_text(payload.get("project_name"), "Project name", 160, True),
        "location": clean_text(payload.get("location"), "Location", 160),
        "hours": hours,
        "note": clean_text(payload.get("note"), "Note", 4000),
    }


def entry_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in ("id", "work_date", "project_number", "project_name", "location", "hours", "note")}


class Handler(BaseHTTPRequestHandler):
    server_version = "WorkLog/1.0"

    def send_json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> object:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request size.") from exc
        if length < 1 or length > MAX_BODY:
            raise ValueError("Request must contain a JSON body under 64 KB.")
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(RESOURCE_ROOT / "static" / "index.html", "text/html; charset=utf-8")
        elif parsed.path == "/app.css":
            self.serve_file(RESOURCE_ROOT / "static" / "app.css", "text/css; charset=utf-8")
        elif parsed.path == "/app.js":
            self.serve_file(RESOURCE_ROOT / "static" / "app.js", "text/javascript; charset=utf-8")
        elif parsed.path == "/api/entries":
            self.get_entries(parse_qs(parsed.query))
        elif parsed.path == "/api/stats":
            self.get_stats(parse_qs(parsed.query))
        elif parsed.path == "/api/export.csv":
            self.export_csv(parse_qs(parsed.query))
        elif parsed.path == "/api/export-annual.pdf":
            self.export_annual_report(parse_qs(parsed.query))
        else:
            self.send_json({"error": "Not found."}, 404)

    def serve_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_json({"error": "App file not found."}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def date_range(query: dict[str, list[str]]) -> tuple[str, str]:
        try:
            start = valid_date(query.get("start", [""])[0])
            end = valid_date(query.get("end", [""])[0])
        except ValueError as exc:
            raise ValueError("Choose a valid start and end date.") from exc
        if start > end:
            raise ValueError("Start date must be on or before end date.")
        return start, end

    def get_entries(self, query: dict[str, list[str]]) -> None:
        try:
            start, end = self.date_range(query)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with db_session() as db:
            rows = db.execute(
                "SELECT id, work_date, project_number, project_name, location, hours, note "
                "FROM entries WHERE work_date BETWEEN ? AND ? ORDER BY work_date, id",
                (start, end),
            ).fetchall()
        self.send_json([entry_dict(row) for row in rows])

    def get_stats(self, query: dict[str, list[str]]) -> None:
        try:
            start, end = self.date_range(query)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with db_session() as db:
            totals = db.execute(
                "SELECT COALESCE(SUM(hours), 0) AS hours, "
                "SUM(CASE WHEN lower(note) LIKE '%relay%' THEN 1 ELSE 0 END) AS relay_records, "
                "COUNT(DISTINCT work_date) AS days FROM entries WHERE work_date BETWEEN ? AND ?",
                (start, end),
            ).fetchone()
            projects = db.execute(
                "SELECT project_number, project_name, SUM(hours) AS hours, "
                "SUM(CASE WHEN lower(note) LIKE '%relay%' THEN 1 ELSE 0 END) AS relay_records "
                "FROM entries WHERE work_date BETWEEN ? AND ? "
                "GROUP BY project_number, project_name ORDER BY hours DESC, project_name COLLATE NOCASE",
                (start, end),
            ).fetchall()
        self.send_json({
            "start": start,
            "end": end,
            "hours": round(totals["hours"], 2),
            "relay_records": totals["relay_records"],
            "days": totals["days"],
            "projects": [dict(row) for row in projects],
        })

    def export_csv(self, query: dict[str, list[str]]) -> None:
        try:
            start, end = self.date_range(query)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with db_session() as db:
            rows = db.execute(
                "SELECT work_date, project_number, project_name, location, hours, note "
                "FROM entries WHERE work_date BETWEEN ? AND ? ORDER BY work_date, id",
                (start, end),
            ).fetchall()
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Date", "Project Number", "Project Name", "Location", "Hours", "Note"])
        writer.writerows([tuple(row) for row in rows])
        body = ("\ufeff" + output.getvalue()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="worklog-{start}-to-{end}.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def export_annual_report(self, query: dict[str, list[str]]) -> None:
        year_value = query.get("year", [""])[0]
        if not re.fullmatch(r"\d{4}", year_value) or not 1 <= int(year_value) <= 9999:
            self.send_json({"error": "Choose a valid four-digit year."}, 400)
            return
        year = int(year_value)
        start, end = f"{year:04d}-01-01", f"{year:04d}-12-31"
        try:
            with db_session() as db:
                rows = db.execute(
                    "SELECT work_date, project_number, project_name, location, hours, note "
                    "FROM entries WHERE work_date BETWEEN ? AND ? ORDER BY work_date, id",
                    (start, end),
                ).fetchall()
            report_path = build_annual_report(
                year,
                [dict(row) for row in rows],
                APP_DATA_DIR / "Year Report" / str(year),
            )
            body = report_path.read_bytes()
        except OSError as exc:
            self.send_json({"error": f"Could not save the annual report: {exc}"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{year}worklog.pdf"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/entries":
            self.send_json({"error": "Not found."}, 404)
            return
        try:
            payload = self.read_json()
            entry = parse_entry(payload)
            end_date = valid_date(payload.get("end_date", entry["work_date"])) if isinstance(payload, dict) else entry["work_date"]
            start_day = date.fromisoformat(entry["work_date"])
            end_day = date.fromisoformat(end_date)
            if end_day < start_day:
                raise ValueError("End date must be on or after the start date.")
            if (end_day - start_day).days > 365:
                raise ValueError("Date range cannot be longer than 366 days.")
            entries = [
                {**entry, "work_date": (start_day + timedelta(days=offset)).isoformat()}
                for offset in range((end_day - start_day).days + 1)
            ]
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with db_session() as db:
            inserted_ids = []
            for daily_entry in entries:
                cursor = db.execute(
                    "INSERT INTO entries (work_date, project_number, project_name, location, hours, note) "
                    "VALUES (:work_date, :project_number, :project_name, :location, :hours, :note)", daily_entry,
                )
                inserted_ids.append(cursor.lastrowid)
            rows = db.execute(
                "SELECT id, work_date, project_number, project_name, location, hours, note "
                f"FROM entries WHERE id IN ({','.join('?' for _ in inserted_ids)}) ORDER BY work_date, id",
                inserted_ids,
            ).fetchall()
        self.send_json([entry_dict(row) for row in rows], 201)

    def do_PUT(self) -> None:
        match = re.fullmatch(r"/api/entries/(\d+)", urlparse(self.path).path)
        if not match:
            self.send_json({"error": "Not found."}, 404)
            return
        try:
            entry = parse_entry(self.read_json())
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with db_session() as db:
            db.execute(
                "UPDATE entries SET work_date=:work_date, project_number=:project_number, "
                "project_name=:project_name, location=:location, hours=:hours, note=:note WHERE id=:id",
                {**entry, "id": int(match.group(1))},
            )
            row = db.execute(
                "SELECT id, work_date, project_number, project_name, location, hours, note "
                "FROM entries WHERE id=?", (int(match.group(1)),),
            ).fetchone()
        if row is None:
            self.send_json({"error": "Record not found."}, 404)
        else:
            self.send_json(entry_dict(row))

    def do_DELETE(self) -> None:
        match = re.fullmatch(r"/api/entries/(\d+)", urlparse(self.path).path)
        if not match:
            self.send_json({"error": "Not found."}, 404)
            return
        with db_session() as db:
            cursor = db.execute("DELETE FROM entries WHERE id=?", (int(match.group(1)),))
        if cursor.rowcount == 0:
            self.send_json({"error": "Record not found."}, 404)
        else:
            self.send_json({"deleted": True})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    initialize()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    print(f"Work Log running on http://{HOST}:{PORT}")
    print(f"Database: {DB_PATH}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWork Log stopped.")

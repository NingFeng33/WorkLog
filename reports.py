"""Build compact annual worklog PDFs using only the Python standard library."""

from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path


PAGE_W, PAGE_H = 595, 842
GREEN = (0.16, 0.37, 0.27)
MUTED = (0.40, 0.46, 0.42)
LIGHT = (0.91, 0.94, 0.91)
PALE = (0.96, 0.97, 0.95)
INK = (0.13, 0.18, 0.14)


def _pdf_text(value: object) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    text = text.encode("cp1252", "replace").decode("cp1252")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class Page:
    def __init__(self) -> None:
        self.commands: list[str] = []

    @staticmethod
    def _color(color: tuple[float, float, float]) -> str:
        return " ".join(f"{channel:.3f}" for channel in color)

    def text(self, x: float, y: float, value: object, size: float = 10,
             color: tuple[float, float, float] = INK, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        self.commands.append(
            f"BT /{font} {size:.2f} Tf {self._color(color)} rg 1 0 0 1 "
            f"{x:.2f} {PAGE_H-y-size:.2f} Tm ({_pdf_text(value)}) Tj ET"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float,
             color: tuple[float, float, float] = LIGHT, width: float = 0.7) -> None:
        self.commands.append(
            f"{self._color(color)} RG {width:.2f} w {x1:.2f} {PAGE_H-y1:.2f} m "
            f"{x2:.2f} {PAGE_H-y2:.2f} l S"
        )

    def rect(self, x: float, y: float, w: float, h: float,
             color: tuple[float, float, float], stroke: bool = False) -> None:
        mode = "B" if stroke else "f"
        self.commands.append(
            f"{self._color(color)} rg {self._color(color)} RG {x:.2f} "
            f"{PAGE_H-y-h:.2f} {w:.2f} {h:.2f} re {mode}"
        )

    def finish(self) -> bytes:
        return ("\n".join(self.commands) + "\n").encode("cp1252", "replace")


def _draw_header(page: Page, title: str, subtitle: str = "") -> None:
    page.text(42, 28, "WORK LOG  /  ANNUAL REPORT", 8, GREEN, True)
    page.text(42, 48, title, 22, INK, True)
    if subtitle:
        page.text(42, 76, subtitle, 9, MUTED)
    page.line(42, 96, PAGE_W-42, 96)


def _draw_footer(page: Page, index: int, total: int, year: int) -> None:
    page.line(42, 813, PAGE_W-42, 813)
    page.text(42, 820, f"{year} Work Log  ·  Generated {date.today().isoformat()}", 7, MUTED)
    page.text(PAGE_W-78, 820, f"{index} / {total}", 7, MUTED)


def _metric(page: Page, x: float, y: float, width: float, label: str, value: object) -> None:
    page.rect(x, y, width, 56, PALE)
    page.text(x+11, y+10, label.upper(), 7, MUTED, True)
    page.text(x+11, y+26, value, 17, GREEN, True)


def _short(value: object, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:max(0, limit-1)].rstrip() + "…"


def _draw_bars(page: Page, values: list[float], labels: list[str], x: float, y: float,
               width: float, height: float, label_every: int = 1) -> None:
    page.line(x, y+height, x+width, y+height, LIGHT)
    maximum = max(values, default=0)
    if maximum <= 0:
        page.text(x+4, y+height/2, "No recorded hours in this period.", 9, MUTED)
        return
    gap = 4 if len(values) < 16 else 2
    bar_w = max(2, (width-gap*(len(values)-1))/max(1, len(values)))
    for i, value in enumerate(values):
        bar_h = (height-18) * value / maximum if value else 0
        bx = x+i*(bar_w+gap)
        if bar_h:
            page.rect(bx, y+height-1-bar_h, bar_w, bar_h, GREEN if value else LIGHT)
        if i % label_every == 0:
            page.text(bx, y+height+4, labels[i], 6.5, MUTED)
    page.text(x, y-11, f"Peak: {maximum:g} hours", 7, MUTED)


def _draw_calendar(page: Page, year: int, month: int,
                   by_day: dict[int, list[dict]]) -> None:
    x0, y0, grid_w, row_h = 42, 378, PAGE_W-84, 61
    col_w = grid_w/7
    for col, label in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
        page.text(x0+col*col_w+4, y0, label, 7, MUTED, True)
    _first_weekday, days_in_month = calendar.monthrange(year, month)
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    top = y0+18
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x, y = x0+c*col_w, top+r*row_h
            page.rect(x, y, col_w, row_h, PALE if day else (1, 1, 1), stroke=True)
            if not day:
                continue
            rows = by_day.get(day, [])
            total = sum(float(row["hours"]) for row in rows)
            page.text(x+4, y+3, f"{day:02d}", 8, INK, True)
            if rows:
                page.text(x+col_w-31, y+3, f"{total:g}h", 7, GREEN, True)
            for i, row in enumerate(rows[:2]):
                note = _short(row.get("note", ""), 16)
                project = _short(row.get("project_number", ""), 12)
                label = f"{project} {float(row['hours']):g}h"
                page.text(x+4, y+16+i*20, label, 6.2, MUTED)
                if note:
                    page.text(x+4, y+24+i*20, note, 5.8, GREEN)
            if len(rows) > 2:
                page.text(x+4, y+53, f"+{len(rows)-2} more", 5.8, MUTED)


def _make_pdf(streams: list[bytes]) -> bytes:
    objects: list[bytes] = []

    def add(value: bytes) -> int:
        objects.append(value)
        return len(objects)

    catalog_id = add(b"")
    pages_id = add(b"")
    regular_font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold_font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for stream in streams:
        content_id = add(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        )
        page_id = add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 {regular_font} 0 R /F2 {bold_font} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode("ascii")
        )
        page_ids.append(page_id)
    objects[catalog_id-1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id-1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)


def build_annual_report(year: int, rows: list[dict], output_dir: Path) -> Path:
    """Save and return the annual PDF path."""
    monthly = [0.0] * 12
    monthly_days = [set() for _ in range(12)]
    monthly_relay = [0] * 12
    projects: dict[tuple[str, str], dict] = {}
    by_month: dict[int, dict[int, list[dict]]] = {m: {} for m in range(1, 13)}
    daily_hours: dict[tuple[int, int], float] = {}
    relay_records = 0
    for row in rows:
        work_day = date.fromisoformat(row["work_date"])
        month = work_day.month
        hours = float(row["hours"])
        monthly[month-1] += hours
        monthly_days[month-1].add(work_day.day)
        daily_hours[(month, work_day.day)] = daily_hours.get((month, work_day.day), 0) + hours
        by_month[month][work_day.day] = by_month[month].get(work_day.day, []) + [row]
        has_relay = "relay" in str(row.get("note", "")).lower()
        if has_relay:
            relay_records += 1
            monthly_relay[month-1] += 1
        key = (str(row["project_number"]), str(row["project_name"]))
        bucket = projects.setdefault(key, {"hours": 0.0, "records": 0, "relay": 0})
        bucket["hours"] += hours
        bucket["records"] += 1
        bucket["relay"] += int(has_relay)

    total_hours = sum(monthly)
    total_days = len({row["work_date"] for row in rows})
    project_rows = sorted(projects.items(), key=lambda item: (-item[1]["hours"], item[0][1].lower()))
    pages: list[Page] = []

    # Year overview and annual analysis.
    page = Page()
    _draw_header(page, f"{year} Work Log", "Year overview and analysis")
    card_w = (PAGE_W-84-30)/4
    _metric(page, 42, 112, card_w, "Total hours", f"{total_hours:g}")
    _metric(page, 52+card_w, 112, card_w, "Work days", total_days)
    _metric(page, 62+card_w*2, 112, card_w, "Projects", len(projects))
    _metric(page, 72+card_w*3, 112, card_w, "Relay notes", relay_records)
    page.text(42, 194, "Hours by month", 13, INK, True)
    _draw_bars(page, monthly, [calendar.month_abbr[m] for m in range(1, 13)], 54, 220, PAGE_W-108, 172)
    page.text(42, 445, "Project summary", 13, INK, True)
    page.text(42, 468, "Project", 7, MUTED, True)
    page.text(375, 468, "HOURS", 7, MUTED, True)
    page.text(448, 468, "RELAY NOTES", 7, MUTED, True)
    page.line(42, 482, PAGE_W-42, 482)
    if not project_rows:
        page.text(42, 500, "No work records were found for this year.", 9, MUTED)
    for i, ((number, name), totals) in enumerate(project_rows[:12]):
        y = 490+i*23
        page.text(42, y, _short(f"{number}  ·  {name}", 66), 8, INK)
        page.text(375, y, f"{totals['hours']:g}", 8, GREEN, True)
        page.text(458, y, totals["relay"], 8, MUTED)
        page.line(42, y+17, PAGE_W-42, y+17)
    if len(project_rows) > 12:
        page.text(42, 780, f"Showing 12 of {len(project_rows)} projects; monthly pages include project details.", 7, MUTED)
    pages.append(page)

    # Each monthly analysis page combines a daily-hours chart and a full calendar.
    for month in range(1, 13):
        page = Page()
        month_name = calendar.month_name[month]
        _draw_header(page, f"{month_name} {year}", "Monthly analysis and calendar")
        days_in_month = calendar.monthrange(year, month)[1]
        month_rows = [row for row in rows if int(row["work_date"][5:7]) == month]
        month_projects: dict[tuple[str, str], float] = {}
        for row in month_rows:
            key = (str(row["project_number"]), str(row["project_name"]))
            month_projects[key] = month_projects.get(key, 0) + float(row["hours"])
        metrics = [
            ("Hours", f"{monthly[month-1]:g}"),
            ("Work days", len(monthly_days[month-1])),
            ("Projects", len(month_projects)),
            ("Relay notes", monthly_relay[month-1]),
        ]
        for i, (label, value) in enumerate(metrics):
            _metric(page, 42+i*128, 108, 119, label, value)
        page.text(42, 171, "Daily hours", 11, INK, True)
        _draw_bars(
            page,
            [daily_hours.get((month, day), 0) for day in range(1, days_in_month+1)],
            [str(day) for day in range(1, days_in_month+1)],
            50, 211, PAGE_W-100, 105, label_every=2 if days_in_month > 20 else 1,
        )
        page.text(42, 344, "Work calendar", 11, INK, True)
        _draw_calendar(page, year, month, by_month[month])
        top_projects = sorted(month_projects.items(), key=lambda item: (-item[1], item[0][1].lower()))[:3]
        if top_projects:
            summary = "Top projects: " + "  |  ".join(
                f"{number} {hours:g}h" for (number, _name), hours in top_projects
            )
            page.text(42, 798, _short(summary, 96), 6.4, MUTED)
        pages.append(page)

    streams = []
    for index, report_page in enumerate(pages, start=1):
        _draw_footer(report_page, index, len(pages), year)
        streams.append(report_page.finish())
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{year}worklog.pdf"
    destination.write_bytes(_make_pdf(streams))
    return destination

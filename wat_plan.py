#!/usr/bin/env python3
"""
Pobiera plan zajęć grupy z planzajec.wcy.wat.edu.pl i zapisuje go jako plik
kalendarza plan.ics (do subskrypcji na iPhonie).

Użycie:  python wat_plan.py [GRUPA] [PLIK_WYJSCIOWY]
Domyślnie: WCY24KC2S1 -> plan.ics
"""
import re
import sys
import hashlib
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

GROUP = sys.argv[1] if len(sys.argv) > 1 else "WCY24KC2S1"
OUT = sys.argv[2] if len(sys.argv) > 2 else "plan.ics"
URL = f"https://planzajec.wcy.wat.edu.pl/pl/rozklad?grupa_id={GROUP}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}

# Godziny bloków (pon–pt oraz weekend – bloki 5–7 różnią się w weekend)
WEEKDAY_BLOCKS = {
    1: ("08:00", "09:35"), 2: ("09:50", "11:25"), 3: ("11:40", "13:15"),
    4: ("13:30", "15:05"), 5: ("16:00", "17:35"), 6: ("17:50", "19:25"),
    7: ("19:40", "21:15"),
}
WEEKEND_BLOCKS = {
    **WEEKDAY_BLOCKS,
    5: ("15:20", "16:55"), 6: ("17:10", "18:45"), 7: ("19:00", "20:35"),
}

# Wzorzec jednego zajęcia w tekście strony, np.:
# 2026_10_01 block2 Swb (w) 307 S Mu[1] Systemy wbudowane - (Wykład) - Murawski Krzysztof #CD5C5C Mu
LESSON_RE = re.compile(
    r"(?P<date>\d{4}_\d{2}_\d{2})\s*block(?P<block>\d)\s*"
    r"(?P<short>\S+?)\s*\((?P<kind>[^)]{1,3})\)\s*"
    r"(?P<room>\S+ \S+)\s+"
    r"(?P<tshort>[^\s\[\]]*)\s*\[(?P<num>\d+)\]\s*"
    r"(?P<name>.+?)\s+-\s+\((?P<type>[^)]+)\)\s+-\s*(?P<teacher>[^#]*?)\s*"
    r"#[0-9A-Fa-f]{6}",
    re.S,
)

# Słowa typowe dla stron z ochroną antybotową
BOT_MARKERS = (
    "captcha", "cloudflare", "cf-chl", "just a moment", "checking your browser",
    "anubis", "access denied", "attention required", "ddos", "verify you are human",
)


def parse(text: str):
    lessons, seen = [], set()
    for m in LESSON_RE.finditer(text):
        d = m.groupdict()
        key = (d["date"], d["block"])
        if key in seen:
            continue
        seen.add(key)
        lessons.append({k: " ".join(v.split()) for k, v in d.items()})
    return lessons


def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    # Linie ICS max 75 bajtów
    out, cur = [], b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > 73:
            out.append(cur.decode())
            cur = b" " + b
        else:
            cur += b
    out.append(cur.decode())
    return "\r\n".join(out)


def build_ics(lessons) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//wat-plan//PL", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:Plan WAT {GROUP}", "X-WR-TIMEZONE:Europe/Warsaw",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H",
        "BEGIN:VTIMEZONE", "TZID:Europe/Warsaw",
        "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
        "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
        "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
        "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for l in lessons:
        day = datetime.strptime(l["date"], "%Y_%m_%d")
        blocks = WEEKEND_BLOCKS if day.weekday() >= 5 else WEEKDAY_BLOCKS
        start, end = blocks[int(l["block"])]
        ymd = day.strftime("%Y%m%d")
        uid = hashlib.md5(f"{GROUP}-{l['date']}-{l['block']}".encode()).hexdigest()
        summary = f"{l['name']} ({l['kind']})"
        desc = f"{l['type']} nr {l['num']}\\nProwadzący: {l['teacher'] or '—'}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@wat-plan",
            f"DTSTAMP:{now}",
            f"DTSTART;TZID=Europe/Warsaw:{ymd}T{start.replace(':', '')}00",
            f"DTEND;TZID=Europe/Warsaw:{ymd}T{end.replace(':', '')}00",
            fold(f"SUMMARY:{ics_escape(summary)}"),
            fold(f"LOCATION:{ics_escape(l['room'])}"),
            fold(f"DESCRIPTION:{desc}"),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def fetch() -> str:
    try:
        r = requests.get(URL, timeout=60, headers=HEADERS)
    except requests.RequestException as e:
        sys.exit(f"BŁĄD POŁĄCZENIA z {URL}: {type(e).__name__}: {e}")

    print(f"URL:          {r.url}")
    print(f"Status HTTP:  {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Server:       {r.headers.get('Server')}")
    print(f"Rozmiar:      {len(r.text)} znaków")

    if r.status_code != 200:
        print("----- początek odpowiedzi -----")
        print(r.text[:1500])
        print("----- koniec podglądu -----")
        sys.exit(f"Serwer zwrócił status {r.status_code}. Plik NIE został nadpisany.")
    return r.text


def main():
    html = fetch()
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    lessons = parse(text)

    if not lessons:
        low = html.lower()
        found = [m for m in BOT_MARKERS if m in low]
        print("----- tekst strony (pierwsze 1500 znaków) -----")
        print(" ".join(text.split())[:1500])
        print("----- koniec podglądu -----")
        if found:
            sys.exit(
                f"Strona wygląda na blokadę antybotową (znaleziono: {', '.join(found)}). "
                "Plik NIE został nadpisany."
            )
        if "block" not in text and not re.search(r"\d{4}_\d{2}_\d{2}", text):
            sys.exit(
                "Strona nie zawiera żadnych zajęć – pusty plan dla tej grupy "
                "(nowy semestr / zmieniona nazwa grupy?). Plik NIE został nadpisany."
            )
        sys.exit("Zajęcia są na stronie, ale regex ich nie rozpoznał – zmienił się format. "
                 "Plik NIE został nadpisany.")

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(lessons))
    print(f"Zapisano {len(lessons)} zajęć do {OUT}")


if __name__ == "__main__":
    main()

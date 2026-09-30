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


def main():
    html = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).text
    text = BeautifulSoup(html, "html.parser").get_text(" ")
    lessons = parse(text)
    if not lessons:
        sys.exit("Nie znaleziono żadnych zajęć – zmienił się układ strony? Plik NIE został nadpisany.")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(lessons))
    print(f"Zapisano {len(lessons)} zajęć do {OUT}")


if __name__ == "__main__":
    main()

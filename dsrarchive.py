#!/usr/bin/env python3
"""DSRArchive – findet Bosskämpfe in Stream-Videos und legt sie in eine Datenbank.

Die Lebensleiste zeigt im Randomizer den Namen des ORIGINAL-Platzes. namen.json
(aus dsr_enemies.json des Trackers) sagt, welcher Gegner dort im Randomizer steht.

Befehle:
  scan QUELLE   Video auswerten (Datei oder Twitch-Adresse) und in die Datenbank schreiben
  export        Datenbank als JSON für die Webseite (docs/kaempfe.json) schreiben
  suche TEXT    in der Datenbank nach Boss/Streamer/Gebiet suchen

Voraussetzungen: Python 3, Pillow (pip install pillow), ffmpeg + ffprobe und tesseract
im PATH (für deutschen Spieltext die Sprachdatei deu), für Adressen zusätzlich yt-dlp.
"""
import argparse, difflib, json, os, re, sqlite3, subprocess, sys, tempfile, unicodedata
from datetime import datetime

from PIL import Image

HIER = os.path.dirname(os.path.abspath(__file__))
BREITE = 1920      # Breite, auf die der durchsuchte Bildbereich skaliert wird
BEREICH_Y = 0.55   # durchsucht wird der untere Teil des Bildes ab dieser Höhe (0..1)
LINK_VORLAUF = 10  # Sekunden vor Kampfbeginn, auf die der Link zeigt
TMP = tempfile.mkdtemp(prefix="dsrarchiv_")

# Bildfilter: Texterkennung klappt je nach Hintergrund mit anderem Filter besser,
# darum werden mehrere probiert und der beste Namenstreffer gewinnt.
VARIANTEN = {
    "plain": lambda b: b,
    "hell170": lambda b: b.point(lambda v: 0 if v > 170 else 255),
    "hell200": lambda b: b.point(lambda v: 0 if v > 200 else 255),
}


# ---------------------------------------------------------------- Namen und Vergleich
def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def lade_namen(pfad):
    """norm. Name (Original DE/EN) -> Liste der Plätze, die so heißen."""
    namen = {}
    for r in json.load(open(pfad, encoding="utf-8")):
        for n in (r["de"], r["en"]):
            if n:
                namen.setdefault(norm(n), []).append(r)
    return namen


def vergleiche(text, namen, schwelle):
    """Bester Namenstreffer für einen Text: (Name, Ähnlichkeit) oder (None, bester Wert)."""
    t = norm(text)
    if len(t) < 5:
        return None, 0
    sm = difflib.SequenceMatcher(autojunk=False)
    sm.set_seq2(t)
    best, bs = None, 0
    for n in namen:
        if abs(len(n) - len(t)) > max(4, len(n) * 0.35):
            continue
        sm.set_seq1(n)
        if sm.real_quick_ratio() < schwelle or sm.quick_ratio() < schwelle:
            continue
        s = sm.ratio()
        if s > bs:
            best, bs = n, s
    if bs < schwelle and len(t) >= 9 and " " in t:
        # Teilname: die Leiste ist teils schlecht lesbar, nur der Anfang kommt an
        # ("Chaos Witch" statt "Chaos Witch Quelaag"). Strenger prüfen, Abzug beim Wert.
        for n in namen:
            if len(n) > len(t) + 2:
                s = difflib.SequenceMatcher(None, t, n[:len(t)], autojunk=False).ratio() * 0.93
                if s > bs:
                    best, bs = n, s
    return (best, bs) if bs >= schwelle else (None, bs)


# ---------------------------------------------------------------- Texterkennung
def tesseract_zeilen(pfad, sprache, psm):
    """Wörter mit Position, nach Textzeile gruppiert."""
    r = subprocess.run(["tesseract", pfad, "stdout", "-l", sprache, "--psm", str(psm), "tsv"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    zeilen = {}
    for l in r.stdout.splitlines()[1:]:
        p = l.split("\t")
        if len(p) < 12 or p[0] != "5" or not p[11].strip():
            continue
        zeilen.setdefault(tuple(p[1:5]), []).append(
            (int(p[6]), int(p[7]), int(p[8]), int(p[9]), p[11].strip()))
    return zeilen


def finde_namen(img, namen, sprache, schwelle, psm=11):
    """Sucht im Bild (Graustufen) nach einem Bossnamen. Gibt den besten Treffer
    {score, rows, text, box, variante} oder None zurück."""
    best = None
    for vname, filt in VARIANTEN.items():
        pfad = os.path.join(TMP, "f.png")
        filt(img).save(pfad)
        for wörter in tesseract_zeilen(pfad, sprache, psm).values():
            wörter.sort()
            for i in range(len(wörter)):
                for j in range(i, min(i + 5, len(wörter))):
                    text = " ".join(w[4] for w in wörter[i:j + 1])
                    n, s = vergleiche(text, namen, schwelle)
                    if n and (best is None or s > best["score"]):
                        l = min(w[0] for w in wörter[i:j + 1])
                        o = min(w[1] for w in wörter[i:j + 1])
                        r = max(w[0] + w[2] for w in wörter[i:j + 1])
                        u = max(w[1] + w[3] for w in wörter[i:j + 1])
                        best = {"score": s, "rows": namen[n], "text": text,
                                "box": [l, o, r - l, u - o], "variante": vname}
        if best and best["score"] >= 0.97:
            break
    return best


# ---------------------------------------------------------------- Video lesen
def video_info(quelle):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", quelle],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d.get("format", {}).get("duration") or 0)


def _vf(w, h):
    ch = int(h * (1 - BEREICH_Y)) // 2 * 2
    sh = max(2, round(BREITE * ch / w / 2) * 2)
    return f"crop={w}:{ch}:0:{h - ch},scale={BREITE}:{sh},format=gray", sh


def _lies(f, n):
    buf = b""
    while len(buf) < n:
        stück = f.read(n - len(buf))
        if not stück:
            return None
        buf += stück
    return buf


def bilder(quelle, w, h, intervall, start=0):
    """Liefert alle `intervall` Sekunden den unteren Bildbereich als Graustufenbild."""
    vf, sh = _vf(w, h)
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", quelle,
           "-vf", f"select='eq(n,0)+gt(floor(t/{intervall}),floor(prev_selected_t/{intervall}))',{vf}",
           "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    try:
        while True:
            daten = _lies(p.stdout, BREITE * sh)
            if daten is None:
                break
            yield Image.frombytes("L", (BREITE, sh), daten)
    finally:
        p.kill()


def bild_bei(quelle, w, h, t):
    vf, sh = _vf(w, h)
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(max(0, t)), "-i", quelle,
                        "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    if len(r.stdout) < BREITE * sh:
        return None
    return Image.frombytes("L", (BREITE, sh), r.stdout[:BREITE * sh])


# ---------------------------------------------------------------- Kämpfe bilden
def gruppiere(treffer, luecke):
    """Aufeinanderfolgende Treffer desselben Platzes (Lücke bis `luecke` s) = ein Kampf."""
    kaempfe = []
    for t, hit in treffer:
        key = "+".join(r["key"] for r in hit["rows"])
        k = kaempfe[-1] if kaempfe else None
        if k and k["key"] == key and t - k["ende"] <= luecke:
            k["ende"] = t
            k["score"] = max(k["score"], hit["score"])
            k["treffer"] += 1
        else:
            kaempfe.append({"key": key, "rows": hit["rows"], "start": t, "ende": t,
                            "score": hit["score"], "treffer": 1, "text": hit["text"]})
    return kaempfe


def verfeinere_start(k, quelle, w, h, intervall, namen, sprache, schwelle):
    """Sucht rückwärts in 2-s-Schritten den ersten Zeitpunkt, an dem der Name zu sehen ist."""
    t, fehl, start = k["start"] - 2, 0, k["start"]
    while t >= 0 and t > k["start"] - intervall and fehl < 2:
        img = bild_bei(quelle, w, h, t)
        hit = finde_namen(img, namen, sprache, schwelle) if img else None
        if hit and "+".join(r["key"] for r in hit["rows"]) == k["key"]:
            start, fehl = t, 0
        else:
            fehl += 1
        t -= 2
    k["start"] = start


def zeit_link(twitch_id, sek):
    sek = max(0, int(sek))
    return f"https://www.twitch.tv/videos/{twitch_id}?t={sek // 3600}h{sek // 60 % 60}m{sek % 60}s"


def hms(sek):
    sek = int(sek)
    return f"{sek // 3600}:{sek // 60 % 60:02d}:{sek % 60:02d}"


# ---------------------------------------------------------------- Datenbank
def db_oeffnen(pfad):
    os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
    db = sqlite3.connect(pfad)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY, quelle TEXT UNIQUE, streamer TEXT, twitch_id TEXT,
        titel TEXT, modus TEXT DEFAULT 'randomizer', dauer REAL, gescannt_am TEXT);
    CREATE TABLE IF NOT EXISTS kaempfe (
        id INTEGER PRIMARY KEY, video_id INTEGER REFERENCES videos(id),
        platz TEXT, boss TEXT, gebiet TEXT, rando_de TEXT, rando_en TEXT,
        kandidaten TEXT, start_s REAL, ende_s REAL, konfidenz REAL, treffer INTEGER);
    """)
    return db


def quelle_aufloesen(quelle, a):
    """Gibt (Abspielquelle, Streamer, Titel, Twitch-ID) zurück."""
    streamer, titel, tid = a.streamer, a.titel, a.twitch_id
    src = quelle
    if re.match(r"https?://", quelle):
        m = re.search(r"videos/(\d+)", quelle)
        tid = tid or (m and m.group(1))
        fmt = ["-f", "bestvideo[height<=720]/best[height<=720]/best"]
        r = subprocess.run(["yt-dlp", "-g", *fmt, quelle], capture_output=True, text=True)
        if r.returncode:
            sys.exit("yt-dlp konnte die Adresse nicht auflösen:\n" + r.stderr[-400:])
        src = r.stdout.split()[0]
        r = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(uploader)s\t%(title)s", quelle],
                           capture_output=True, text=True)
        if r.returncode == 0 and "\t" in r.stdout:
            u, t = r.stdout.strip().split("\t", 1)
            streamer, titel = streamer or u, titel or t
    else:
        m = re.search(r"\[?v(\d{6,})\]?", os.path.basename(quelle))
        tid = tid or (m and m.group(1))
    return src, streamer or "unbekannt", titel or os.path.basename(quelle), tid


def scan(a):
    namen = lade_namen(a.namen)
    db = db_oeffnen(a.db)
    src, streamer, titel, tid = quelle_aufloesen(a.quelle, a)
    alt = db.execute("SELECT id FROM videos WHERE quelle=?", (a.quelle,)).fetchone()
    if alt and not a.neu:
        print("Schon in der Datenbank, übersprungen (--neu zum erneuten Auswerten).")
        return
    if alt:
        db.execute("DELETE FROM kaempfe WHERE video_id=?", alt)
        db.execute("DELETE FROM videos WHERE id=?", alt)
    w, h, dauer = video_info(src)
    print(f"{streamer}: {titel} ({w}x{h}, {hms(dauer)}), Twitch-ID: {tid or 'unbekannt'}")
    treffer = []
    for i, img in enumerate(bilder(src, w, h, a.intervall)):
        hit = finde_namen(img, namen, a.lang, a.schwelle)
        if hit:
            treffer.append((i * a.intervall, hit))
            print(f"  {hms(i * a.intervall)}  {hit['text']!r}  {hit['score']:.2f}", file=sys.stderr)
        elif i % 50 == 0:
            print(f"  ... {hms(i * a.intervall)}", file=sys.stderr)
    kaempfe = [k for k in gruppiere(treffer, a.luecke) if k["treffer"] >= 2 or k["score"] >= 0.9]
    for k in kaempfe:
        verfeinere_start(k, src, w, h, a.intervall, namen, a.lang, a.schwelle)
        k["start"] += a.versatz   # Zeiten beziehen sich auf das ganze Twitch-Video
        k["ende"] += a.versatz
    cur = db.execute("INSERT INTO videos(quelle,streamer,twitch_id,titel,modus,dauer,gescannt_am) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (a.quelle, streamer, tid, titel, a.modus, dauer, datetime.now().isoformat(timespec="seconds")))
    vid = cur.lastrowid
    for k in kaempfe:
        r0 = k["rows"][0]
        kand = [{"platz": r["key"], "gebiet": r["area_de"], "pts": r["pts"],
                 "rando_de": r["rando_de"], "rando_en": r["rando_en"]} for r in k["rows"]]
        db.execute("INSERT INTO kaempfe(video_id,platz,boss,gebiet,rando_de,rando_en,kandidaten,"
                   "start_s,ende_s,konfidenz,treffer) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (vid, k["key"], r0["de"], " / ".join(r["area_de"] for r in k["rows"]),
                    " / ".join(r["rando_de"] for r in k["rows"]), " / ".join(r["rando_en"] for r in k["rows"]),
                    json.dumps(kand, ensure_ascii=False), k["start"], k["ende"], round(k["score"], 3), k["treffer"]))
        print(f"{hms(k['start'])}  {r0['de']}  →  Randomizer: {' / '.join(r['rando_de'] for r in k['rows'])}"
              + (f"   {zeit_link(tid, k['start'] - LINK_VORLAUF)}" if tid else ""))
    db.commit()
    print(f"{len(kaempfe)} Kämpfe gespeichert.")


def zeilen_aus_db(db):
    out = []
    for r in db.execute("SELECT v.streamer, v.titel, v.twitch_id, v.modus, k.boss, k.gebiet, k.rando_de,"
                        " k.rando_en, k.start_s, k.konfidenz, k.kandidaten FROM kaempfe k"
                        " JOIN videos v ON v.id=k.video_id ORDER BY v.streamer, v.id, k.start_s"):
        s, titel, tid, modus, boss, gebiet, rd, re_, start, konf, kand = r
        out.append({"streamer": s, "titel": titel, "twitch_id": tid, "modus": modus, "boss": boss,
                    "gebiet": gebiet, "rando_de": rd, "rando_en": re_, "start_s": int(start),
                    "konfidenz": konf, "mehrdeutig": len(json.loads(kand)) > 1,
                    "link": zeit_link(tid, start - LINK_VORLAUF) if tid else None})
    return out


def export(a):
    db = db_oeffnen(a.db)
    zeilen = zeilen_aus_db(db)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump({"stand": datetime.now().strftime("%Y-%m-%d"), "kaempfe": zeilen},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(zeilen)} Kämpfe nach {a.out} geschrieben.")


def suche(a):
    t = norm(a.text)
    for z in zeilen_aus_db(db_oeffnen(a.db)):
        if t in norm(" ".join(str(v) for v in (z["streamer"], z["boss"], z["gebiet"], z["rando_de"], z["rando_en"]))):
            print(f"{z['streamer']:<16} {z['boss']:<28} → {z['rando_de']:<28} {z['link'] or hms(z['start_s'])}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=os.path.join(HIER, "daten", "archiv.db"))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("quelle")
    s.add_argument("--streamer")
    s.add_argument("--titel")
    s.add_argument("--twitch-id")
    s.add_argument("--versatz", type=int, default=0,
                   help="Sekunden, bei denen ein heruntergeladener Ausschnitt im Gesamtvideo beginnt")
    s.add_argument("--modus", default="randomizer")
    s.add_argument("--lang", default="eng")
    s.add_argument("--intervall", type=int, default=20, help="Sekunden zwischen den Stichproben")
    s.add_argument("--luecke", type=int, default=90, help="Sekunden ohne Treffer, bis ein Kampf als beendet gilt")
    s.add_argument("--schwelle", type=float, default=0.85)
    s.add_argument("--namen", default=os.path.join(HIER, "namen.json"))
    s.add_argument("--neu", action="store_true", help="schon vorhandenes Video erneut auswerten")
    s.set_defaults(f=scan)
    e = sub.add_parser("export")
    e.add_argument("--out", default=os.path.join(HIER, "docs", "kaempfe.json"))
    e.set_defaults(f=export)
    q = sub.add_parser("suche")
    q.add_argument("text")
    q.set_defaults(f=suche)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()

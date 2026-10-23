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
import argparse, difflib, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time, unicodedata
from datetime import datetime

from PIL import Image, ImageFilter

HIER = os.path.dirname(os.path.abspath(__file__))
BREITE_MAX = 1920  # größte Breite, auf die der durchsuchte Bildbereich hochskaliert wird
VOLLSUCHE_ALLE = 6 # bei bekannter Namensposition nur jede n-te Stichprobe das ganze Bild durchsuchen
BEREICH_Y = 0.55   # durchsucht wird der untere Teil des Bildes ab dieser Höhe (0..1)
LINK_VORLAUF = 10  # Sekunden vor Kampfbeginn, auf die der Link zeigt
TMP = tempfile.mkdtemp(prefix="dsrarchiv_")

# Bildfilter: Texterkennung klappt je nach Hintergrund mit anderem Filter besser,
# darum werden mehrere probiert und der beste Namenstreffer gewinnt.
VARIANTEN = {
    # schärfen + hell/dunkel trennen: an echten Videos (480p und 720p) mit Abstand am besten
    "scharf170": lambda b: b.filter(ImageFilter.UnsharpMask(2, 150, 3)).point(lambda v: 0 if v > 170 else 255),
    "hell130": lambda b: b.point(lambda v: 0 if v > 130 else 255),
    "plain": lambda b: b,
}


# ---------------------------------------------------------------- Namen und Vergleich
def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


# Plätze, an deren Leiste andere Namen stehen als im Listeneintrag. Anor Londo ist in der Liste
# ein gemeinsamer Eintrag, an der Leiste stehen aber zwei einzelne Namen.
ZUSATZNAMEN = {"11-1": ["Dragon Slayer Ornstein", "Executioner Smough"],
               "2-4": ["Bell Gargoyle"]}   # an der Leiste steht die Einzahl (am Video belegt)


def lade_namen(pfad, deutsch=False):
    """norm. Name -> {"anzeige": Name, "kandidaten": [...]}.

    Ein Name kann an der Leiste stehen, weil er der Name des Original-Platzes ist
    ("platz") oder weil der Randomizer bei manchen Ersetzungen den Namen des
    Ersatz-Gegners mitändert ("ersatz"). Welche Deutung stimmt, sagt der Name allein
    nicht, deshalb werden alle möglichen gespeichert.
    """
    namen = {}

    def eintrag(name, deutung, r):
        if not name:
            return
        e = namen.setdefault(norm(name), {"anzeige": name, "kandidaten": []})
        if any(k["platz"] == r["key"] for k in e["kandidaten"]):
            return  # Original- und Ersatzname gleich (z. B. Havel): nur einmal
        e["kandidaten"].append({"deutung": deutung, "platz": r["key"], "gebiet": r["area_de"],
                                "pts": r["pts"], "original": r["en"], "original_de": r["de"],
                                "rando_de": r["rando_de"], "rando_en": r["rando_en"]})

    daten = json.load(open(pfad, encoding="utf-8"))
    # Plätze mit 3 Punkten sind Mini-Bosse und normale Gegner ohne Namensleiste (laut Matthias).
    # Ihr Platzname steht nie an einer Leiste (Fehltreffer aus Menü- und Chattext, z. B. "Black Knight 1").
    # Als Ersatz-Gegner zählen sie nur, wenn dort ein echter Boss steht (Hydra-Platz mit Gaping Dragon).
    bosse = {norm(r["en"]) for r in daten if r["pts"] >= 5}
    for z in ZUSATZNAMEN.values():
        bosse |= {norm(x) for x in z}
    for r in daten:
        boss_platz = r["pts"] >= 5
        if boss_platz:
            eintrag(r["en"], "platz", r)
            for z in ZUSATZNAMEN.get(r["key"], []):
                eintrag(z, "platz", r)
        if boss_platz or norm(r["rando_en"]) in bosse:
            eintrag(r["rando_en"], "ersatz", r)
        if deutsch:
            if boss_platz:
                eintrag(r["de"], "platz", r)
            if boss_platz or norm(r["rando_en"]) in bosse:
                eintrag(r["rando_de"], "ersatz", r)
    return namen


def gegner_text(c):
    """Der Gegner, der laut dieser Deutung tatsächlich dort steht."""
    return c["rando_en"] if c.get("deutung", "platz") == "platz" else c.get("anzeige") or c["rando_en"]


def deutung_text(c):
    if c.get("deutung", "platz") == "platz":
        return f"Platz {c.get('original', '?')} ({c['gebiet']}), dort steht: {c['rando_en']}"
    return f"Ersatz-Gegner an Platz {c.get('original', '?')} ({c['gebiet']})"


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


# ---------------------------------------------------------------- Leistenprüfung
LEISTENPRUEFUNG = True


def hat_leiste(rgb, box):
    """Prüft, ob unter dem Namen die Lebensleiste des Bosses liegt: ein waagerechtes rotes Band,
    das nahe am linken Namensrand beginnt. Es zählt die längste zusammenhängende rote Strecke
    einer Zeile (mindestens 3 % der Bildbreite), damit auch eine fast leere Leiste erkannt wird.
    Chat, Overlays und Untertitel haben das nicht, so werden Namen in normalem Text nicht als
    Bosskampf gezählt."""
    W, H = rgb.size
    l, o, bw, bh = box
    y0, y1 = min(H, o + bh), min(H, o + bh + max(6, 3 * bh))
    x0, x1 = max(0, l - int(0.02 * W)), min(W, l + int(0.27 * W))
    if y1 - y0 < 2 or x1 - x0 < 20:
        return False
    px = rgb.crop((x0, y0, x1, y1)).load()
    breite = x1 - x0
    mindest = int(0.03 * W)
    fruehester_start = (l - x0) - int(0.007 * W)    # echte Leiste beginnt am Namensrand, nicht weit links davon
    spaetester_start = (l - x0) + int(0.04 * W)
    zeilen = 0
    for y in range(y1 - y0):
        lauf = start = 0
        ok = False
        for x in range(breite):
            r, g, b = px[x, y]
            if r >= 22 and r > 1.8 * (g + 2) and r > 1.8 * (b + 2):   # dunkles Rot der Leiste
                if lauf == 0:
                    start = x
                lauf += 1
                if lauf >= mindest and fruehester_start <= start <= spaetester_start:
                    ok = True
                    break
            else:
                lauf = 0
        if ok:
            zeilen += 1
    return zeilen >= 2


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


def finde_namen(img, namen, sprache, schwelle, psm=11, varianten=None):
    """Sucht im Bild (Graustufen) nach einem Bossnamen. Gibt den besten Treffer
    {score, key, name, kandidaten, text, box, variante} oder None zurück."""
    best, nah = None, 0
    rgb, img = img, img.convert("L")
    for vname, filt in VARIANTEN.items():
        if varianten and vname not in varianten:
            continue
        pfad = os.path.join(TMP, "f.png")
        filt(img).save(pfad)
        for wörter in tesseract_zeilen(pfad, sprache, psm).values():
            wörter.sort()
            for i in range(len(wörter)):
                for j in range(i, min(i + 5, len(wörter))):
                    text = " ".join(w[4] for w in wörter[i:j + 1])
                    n, s = vergleiche(text, namen, schwelle)
                    nah = max(nah, s)
                    laenger = bool(best and best["text"] in text and len(text) > len(best["text"]) and s >= best["score"] - 0.05)
                    if n and (best is None or s > best["score"] or laenger):   # längerer Text mit fast gleichem Wert gewinnt ("Bell Gargoyle" statt "Gargoyle")
                        l = min(w[0] for w in wörter[i:j + 1])
                        o = min(w[1] for w in wörter[i:j + 1])
                        r = max(w[0] + w[2] for w in wörter[i:j + 1])
                        u = max(w[1] + w[3] for w in wörter[i:j + 1])
                        if LEISTENPRUEFUNG and not hat_leiste(rgb, (l, o, r - l, u - o)):
                            continue
                        best = {"score": s, "key": n, "name": namen[n]["anzeige"],
                                "kandidaten": namen[n]["kandidaten"], "text": text,
                                "box": [l, o, r - l, u - o], "variante": vname}
        if best and best["score"] >= 0.97:
            break
        if not best and nah < 0.6:
            break  # nichts Namensähnliches gelesen: weitere Filter bringen bei Bildern ohne Leiste nichts
    return best


# ---------------------------------------------------------------- Video lesen
def video_info(quelle):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", quelle],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return s["width"], s["height"], float(d.get("format", {}).get("duration") or 0)


def breite_fuer(w):
    """Quellen mit kleiner Auflösung (z. B. 480p) werden auf das Doppelte hochskaliert."""
    return min(BREITE_MAX, w * 2) // 2 * 2


def _vf(w, h):
    b = breite_fuer(w)
    ch = int(h * (1 - BEREICH_Y)) // 2 * 2
    sh = max(2, round(b * ch / w / 2) * 2)
    return f"crop={w}:{ch}:0:{h - ch},scale={b}:{sh},format=rgb24", b, sh


def _lies(f, n):
    buf = b""
    while len(buf) < n:
        stück = f.read(n - len(buf))
        if not stück:
            return None
        buf += stück
    return buf


def schluesselbild_abstand(quelle):
    """Mittlerer Abstand der Schlüsselbilder in den ersten 2 Minuten (Sekunden), None wenn unbekannt."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+120",
                        "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", quelle],
                       capture_output=True, text=True)
    zeiten = []
    for l in r.stdout.splitlines():
        p = l.split(",")
        if len(p) >= 2 and "K" in p[1]:
            try:
                zeiten.append(float(p[0]))
            except ValueError:
                pass
    return (zeiten[-1] - zeiten[0]) / (len(zeiten) - 1) if len(zeiten) >= 2 else None


def bilder(quelle, w, h, intervall, zeiten, nur_schluessel=True, bereiche=None):
    """Liefert alle `intervall` Sekunden den unteren Bildbereich als Bild.

    Es werden nur Schlüsselbilder dekodiert (bei Twitch alle 2 Sekunden): das ist etwa
    zehnmal schneller als jedes Bild zu dekodieren. Die echten Zeitpunkte der gelieferten
    Bilder stehen nach Ende der Schleife in `zeiten`.
    `bereiche`: Liste von (von, bis) in Sekunden, nur diese Abschnitte werden gelesen
    (Zeitstempel bleiben die des ganzen Videos). Ohne Angabe wird alles gelesen.
    """
    vf, b, sh = _vf(w, h)
    logpfad = os.path.join(TMP, "ffmpeg.log")
    zeiten.clear()
    for ab, bis in (bereiche or [(None, None)]):
        vorn = ["-ss", str(ab), "-t", str(bis - ab), "-copyts"] if ab is not None else []
        cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info", *(["-skip_frame", "nokey"] if nur_schluessel else []),
               *vorn, "-i", quelle,
               "-vf", f"select='eq(n,0)+gt(floor(t/{intervall}),floor(prev_selected_t/{intervall}))',showinfo,{vf}",
               "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        with open(logpfad, "wb") as log:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log)
            try:
                while True:
                    daten = _lies(p.stdout, b * sh * 3)
                    if daten is None:
                        break
                    yield Image.frombytes("RGB", (b, sh), daten)
            finally:
                p.kill()
        for l in open(logpfad, encoding="utf-8", errors="replace"):
            m = re.search(r"Parsed_showinfo.*?pts_time:\s*([0-9.]+)", l)
            if m:
                zeiten.append(float(m.group(1)))


def bild_bei(quelle, w, h, t):
    vf, b, sh = _vf(w, h)
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(max(0, t)), "-i", quelle,
                        "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    if len(r.stdout) < b * sh * 3:
        return None
    return Image.frombytes("RGB", (b, sh), r.stdout[:b * sh * 3])


def streifen_um(hit, groesse):
    """Bereich um einen gefundenen Namen. Der Name steht linksbündig über der Leiste, seine
    Länge hängt vom Boss ab, deshalb wird nach rechts großzügig Platz gelassen."""
    W, H = groesse
    l, o, bw, bh = hit["box"]
    return (max(0, l - int(0.03 * W)), max(0, o - bh), min(W, l + int(0.5 * W)), min(H, o + 3 * bh))


def suche_mit_streifen(img, kal, namen, sprache, schwelle):
    """Schnelle Suche im bekannten Streifen (ein Bildfilter genügt meist, der zweite als Rückfall)."""
    if not kal:
        return None
    hit = finde_namen(img.crop(kal), namen, sprache, schwelle, varianten=("scharf170", "hell130"))
    if hit:   # Position auf das ganze Bild umrechnen
        hit["box"] = [hit["box"][0] + kal[0], hit["box"][1] + kal[1], hit["box"][2], hit["box"][3]]
    return hit


# ---------------------------------------------------------------- Kämpfe bilden
def gruppiere(treffer, luecke):
    """Aufeinanderfolgende Treffer desselben Platzes (Lücke bis `luecke` s) = ein Kampf."""
    kaempfe = []
    for idx, t, hit in treffer:
        key = hit["key"]
        k = kaempfe[-1] if kaempfe else None
        if k and k["key"] == key and t - k["ende"] <= luecke:
            k["ende"] = t
            k["score"] = max(k["score"], hit["score"])
            k["treffer"] += 1
        else:
            kaempfe.append({"key": key, "name": hit["name"], "kandidaten": hit["kandidaten"],
                            "start": t, "ende": t, "idx": idx,
                            "score": hit["score"], "treffer": 1, "text": hit["text"]})
    return kaempfe


def suche_luecke(k, zeit, voll, quelle, w, h, namen, sprache, schwelle):
    """Stichproben vor dem ersten Treffer, die nur im Streifen gelesen wurden, nochmal mit
    voller Suche prüfen (der Name kann an anderer Stelle stehen, z. B. nach einem Szenenwechsel).
    Gibt (letzte Zeit ohne Name, frühester Zeitpunkt mit Name) zurück."""
    start, j = k["start"], k["idx"] - 1
    while j >= 0:
        if j in voll:
            return zeit(j), start
        img = bild_bei(quelle, w, h, zeit(j))
        hit = finde_namen(img, namen, sprache, schwelle) if img else None
        if hit and hit["key"] == k["key"]:
            start, j = zeit(j), j - 1
            k["treffer"] += 1
        else:
            return zeit(j), start
    return start, start


def verfeinere_start(k, lo, quelle, w, h, namen, sprache, schwelle, kal):
    """Halbiert das Zeitfenster zwischen der letzten Stichprobe ohne und der ersten mit Treffer
    (bis auf 2 Sekunden): so genau wird der Kampfbeginn bestimmt, ohne jede Sekunde zu prüfen."""
    hi = k["start"]
    while hi - lo > 2:
        mitte = (lo + hi) / 2
        img = bild_bei(quelle, w, h, mitte)
        hit = None
        if img:
            hit = suche_mit_streifen(img, kal, namen, sprache, schwelle) or finde_namen(img, namen, sprache, schwelle)
        if hit and hit["key"] == k["key"]:
            hi = mitte
        else:
            lo = mitte
    k["start"] = hi


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
    """Gibt (Abspielquelle, Streamer, Titel, Twitch-ID, Kapitel) zurück. Kapitel: Liste mit start_time, end_time, title (Spielwechsel) oder None."""
    streamer, titel, tid = a.streamer, a.titel, a.twitch_id
    src, kapitel = quelle, None
    if re.match(r"https?://", quelle):
        m = re.search(r"videos/(\d+)", quelle)
        tid = tid or (m and m.group(1))
        hoehe = a.hoehe
        fmt = ["-f", f"bestvideo[height<={hoehe}]/best[height<={hoehe}]/best"]
        r = subprocess.run(["yt-dlp", "-g", *fmt, quelle], capture_output=True, text=True)
        if r.returncode:
            sys.exit("yt-dlp konnte die Adresse nicht auflösen:\n" + r.stderr[-400:])
        src = r.stdout.split()[0]
        r = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(uploader)s\t%(title)s\t%(chapters)j", quelle],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.count("\t") >= 2:
            u, t, ch = r.stdout.strip().split("\t", 2)
            streamer, titel = streamer or u, titel or t
            try:
                kapitel = json.loads(ch) or None
            except ValueError:
                kapitel = None
    else:
        m = re.search(r"\[?v(\d{6,})\]?", os.path.basename(quelle))
        tid = tid or (m and m.group(1))
    return src, streamer or "unbekannt", titel or os.path.basename(quelle), tid, kapitel


def scan(a):
    global LEISTENPRUEFUNG
    LEISTENPRUEFUNG = not a.ohne_leistenpruefung
    namen = lade_namen(a.namen, a.auch_deutsch)
    db = db_oeffnen(a.db)
    alt = db.execute("SELECT id FROM videos WHERE quelle=?", (a.quelle,)).fetchone()
    if alt and not a.neu:
        print("Schon in der Datenbank, übersprungen (--neu zum erneuten Auswerten).")
        return
    src, streamer, titel, tid, kapitel = quelle_aufloesen(a.quelle, a)
    if alt:
        db.execute("DELETE FROM kaempfe WHERE video_id=?", alt)
        db.execute("DELETE FROM videos WHERE id=?", alt)
    w, h, dauer = video_info(src)
    print(f"{streamer}: {titel} ({w}x{h}, {hms(dauer)}), Twitch-ID: {tid or 'unbekannt'}")
    treffer, zeiten, kal, vollsuchen, streifen, voll = [], [], None, 0, 0, set()
    letzter = None   # Index der letzten Stichprobe mit Treffer
    t0 = time.time()
    bereiche = None
    if kapitel and not a.ganzes_video:
        bereiche = spiel_abschnitte(kapitel, a.kapitel, dauer)
        if not bereiche:
            print("  Kein Kapitel mit Dark Souls Remastered, Video übersprungen (--ganzes-video wertet trotzdem aus).")
            return
        print("  Ausgewertet werden nur diese Abschnitte: " + ", ".join(f"{hms(x)}–{hms(y)}" for x, y in bereiche))
    elif not kapitel:
        print("  Keine Kapitel-Angaben, das ganze Video wird ausgewertet.")
    nur_schluessel = True
    if not re.match(r"https?://", a.quelle):
        ab = schluesselbild_abstand(src)
        if ab is None or ab > 6:   # Twitch: alle 2 s; bei seltenen Schlüsselbildern alle Bilder dekodieren
            nur_schluessel = False
            print(f"  Schlüsselbilder nur alle {ab and round(ab)} s: dekodiere alle Bilder (langsamer)", file=sys.stderr)
    for i, img in enumerate(bilder(src, w, h, a.intervall, zeiten, nur_schluessel, bereiche)):
        hit = None
        # Läuft gerade ein Kampf (Treffer vor kurzem)? Nur dann gilt die Namensposition des letzten
        # Treffers. Danach verfällt sie, sonst würde ein neuer Boss an anderer Stelle übersehen
        # (Sif im 6-Stunden-Video), weil nur noch jedes 6. Bild ganz durchsucht würde.
        aktiv = letzter is not None and (i - letzter) * a.intervall <= a.luecke
        if not aktiv:
            kal = None
        if kal and i % VOLLSUCHE_ALLE:
            hit = suche_mit_streifen(img, kal, namen, a.lang, a.schwelle)
            streifen += 1
        # Bei Streifen-Fehlschlag im laufenden Kampf das ganze Bild prüfen
        if not hit and (not kal or i % VOLLSUCHE_ALLE == 0 or aktiv):
            hit = finde_namen(img, namen, a.lang, a.schwelle)
            vollsuchen += 1
            voll.add(i)
        if hit:
            letzter = i
            kal = streifen_um(hit, img.size)
            treffer.append((i, None, hit))
            print(f"  Bild {i}  {hit['text']!r}  {hit['score']:.2f}", file=sys.stderr)
        elif i % 50 == 0:
            print(f"  ... Bild {i}", file=sys.stderr)
    # echte Zeitpunkte der Bilder (Rückfall: gleichmäßiger Abstand)
    zeit = lambda i: zeiten[i] if i < len(zeiten) else i * a.intervall
    treffer = [(i, zeit(i), hit) for i, _, hit in treffer]
    kaempfe = [k for k in gruppiere(treffer, a.luecke) if k["treffer"] >= 2 or k["score"] >= 0.9]
    for k in kaempfe:
        lo, k["start"] = suche_luecke(k, zeit, voll, src, w, h, namen, a.lang, a.schwelle)
        verfeinere_start(k, lo, src, w, h, namen, a.lang, a.schwelle, kal)
    # Kämpfe desselben Namens, die sich nach der Startbestimmung berühren, sind ein Kampf
    kaempfe.sort(key=lambda k: k["start"])
    zusammen = []
    # gleicher Platz zählt wie gleicher Name ("Bell Gargoyle" und "Bell Gargoyles")
    sig = lambda k: frozenset((c["deutung"], c["platz"]) for c in k["kandidaten"])
    for k in kaempfe:
        m = next((x for x in reversed(zusammen) if x["key"] == k["key"] or sig(x) == sig(k)), None)
        if m and k["start"] - m["ende"] <= a.luecke:
            m["ende"] = max(m["ende"], k["ende"])
            m["treffer"] += k["treffer"]
            m["score"] = max(m["score"], k["score"])
        else:
            zusammen.append(k)
    kaempfe = zusammen
    for k in kaempfe:
        k["start"] += a.versatz   # Zeiten beziehen sich auf das ganze Twitch-Video
        k["ende"] += a.versatz
    print(f"Auswertung: {len(zeiten) or 'ca. ' + str(int(dauer / a.intervall))} Stichproben, "
          f"{vollsuchen} volle Suchen, {streifen} Streifen-Suchen, {time.time() - t0:.0f} s",
          file=sys.stderr)
    cur = db.execute("INSERT INTO videos(quelle,streamer,twitch_id,titel,modus,dauer,gescannt_am) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (a.quelle, streamer, tid, titel, a.modus, dauer, datetime.now().isoformat(timespec="seconds")))
    vid = cur.lastrowid
    for k in kaempfe:
        kand = [dict(c, anzeige=k["name"]) for c in k["kandidaten"]]
        gebiete = list(dict.fromkeys(c["gebiet"] for c in kand))
        gegner = list(dict.fromkeys(gegner_text(c) for c in kand))
        db.execute("INSERT INTO kaempfe(video_id,platz,boss,gebiet,rando_de,rando_en,kandidaten,"
                   "start_s,ende_s,konfidenz,treffer) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (vid, k["key"], k["name"], " / ".join(gebiete), "", " / ".join(gegner),
                    json.dumps(kand, ensure_ascii=False), k["start"], k["ende"], round(k["score"], 3), k["treffer"]))
        print(f"{hms(k['start'])}–{hms(k['ende'])}  Leiste: {k['name']}  ({k['treffer']} Treffer)"
              + (f"   {zeit_link(tid, k['start'] - LINK_VORLAUF)}" if tid else ""))
        for c in kand:
            print("      mögliche Deutung:", deutung_text(c))
    db.commit()
    print(f"{len(kaempfe)} Kämpfe gespeichert.")


def zeilen_aus_db(db):
    out = []
    for r in db.execute("SELECT v.streamer, v.titel, v.twitch_id, v.modus, k.boss, k.gebiet, k.rando_de,"
                        " k.rando_en, k.start_s, k.konfidenz, k.kandidaten, k.ende_s, k.treffer FROM kaempfe k"
                        " JOIN videos v ON v.id=k.video_id ORDER BY v.streamer, v.id, k.start_s"):
        s, titel, tid, modus, boss, gebiet, rd, re_, start, konf, kand, ende, treffer = r
        kand = json.loads(kand)
        out.append({"streamer": s, "titel": titel, "twitch_id": tid, "modus": modus, "boss": boss,
                    "gebiet": gebiet, "gegner": re_, "start_s": int(start), "ende_s": int(ende or start),
                    "treffer": treffer, "konfidenz": konf,
                    "deutungen": [deutung_text(dict(c, anzeige=boss)) for c in kand],
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
    zeilen = []
    for z in zeilen_aus_db(db_oeffnen(a.db)):
        if t in norm(" ".join([z["streamer"], z["boss"], z["gebiet"], z["gegner"]] + z["deutungen"])):
            zeilen.append(f"{z['streamer']:<12} {hms(z['start_s'])}–{hms(z['ende_s'])} {z['boss']:<26} {z['treffer']} Treffer  {z['link'] or ''}")
            zeilen += ["       " + d for d in z["deutungen"]]
    if a.out:   # direkt als UTF-8-Datei (die Umleitung > schreibt unter Windows in cp1252 und scheitert an Sonderzeichen)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("\n".join(zeilen) + "\n")
        print(f"{len(zeilen)} Zeilen nach {a.out} geschrieben.")
    else:
        print("\n".join(zeilen))


def kanal_liste(kanal):
    """Die Aufzeichnungen (VODs) eines Kanals, neueste zuerst: [{url, titel, dauer}].
    Nutzt yt-dlp, es sind keine Twitch-Zugangsdaten nötig."""
    name = kanal.rstrip("/").split("/")[-1] if kanal.startswith("http") else kanal
    url = f"https://www.twitch.tv/{name}/videos?filter=archives&sort=time"
    r = subprocess.run(["yt-dlp", "--flat-playlist", "-J", url], capture_output=True, text=True)
    if r.returncode:
        sys.exit("yt-dlp konnte die Videoliste nicht holen:\n" + r.stderr[-400:])
    return liste_parsen(r.stdout)


def liste_parsen(text):
    out = []
    for e in json.loads(text).get("entries") or []:
        url = e.get("url") or e.get("webpage_url") or ""
        if not url.startswith("http") and e.get("id"):
            url = f"https://www.twitch.tv/videos/{str(e['id']).lstrip('v')}"
        if url:
            out.append({"url": url, "titel": e.get("title") or "", "dauer": e.get("duration") or 0})
    return out


def kapitel_von(url):
    """Kapitel (Spielwechsel) eines Twitch-Videos von yt-dlp oder None."""
    r = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(chapters)j", url], capture_output=True, text=True)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1]) or None
    except (ValueError, IndexError):
        return None


def spiel_abschnitte(kapitel, muster, dauer=0):
    """Abschnitte (von, bis) der Kapitel, deren Titel zum Muster passt, mindestens 60 s lang."""
    rx = re.compile(muster, re.I)
    ab = [(max(0, k["start_time"]), min(dauer, k["end_time"]) if dauer else k["end_time"])
          for k in kapitel if rx.search(k.get("title") or "")]
    return [x for x in ab if x[1] - x[0] >= 60]


def scan_kanal(a):
    """Wertet die letzten Aufzeichnungen eines Kanals nacheinander aus."""
    videos = kanal_liste(a.kanal)
    if a.titel_filter:
        rx = re.compile(a.titel_filter, re.I)
        videos = [v for v in videos if rx.search(v["titel"])]
    videos = [v for v in videos if not v["dauer"] or v["dauer"] >= a.min_dauer * 60]
    videos = videos[:a.max]
    print(f"{len(videos)} Videos von {a.kanal}:")
    for v in videos:
        zusatz = ""
        if a.nur_liste:
            kap = kapitel_von(v["url"])
            if not kap:
                zusatz = "  [keine Kapitel-Angaben]"
            else:
                ab = spiel_abschnitte(kap, a.kapitel, v["dauer"])
                zusatz = ("  [Dark Souls: " + hms(sum(y - x for x, y in ab)) + "]") if ab else "  [kein Dark Souls]"
        print(f"  {hms(v['dauer'])}  {v['titel'][:70]}  {v['url']}{zusatz}")
    if a.nur_liste:
        return
    for i, v in enumerate(videos, 1):
        print(f"\n=== Video {i} von {len(videos)}: {v['titel'][:70]}")
        b = argparse.Namespace(**vars(a))
        b.quelle, b.streamer, b.titel, b.twitch_id = v["url"], None, None, None
        try:
            scan(b)
        except SystemExit as e:
            print(f"  übersprungen: {e}", file=sys.stderr)
        except KeyboardInterrupt:
            print("\nAbgebrochen. Fertig ausgewertete Videos bleiben gespeichert, das laufende Video nicht.")
            raise


def scan_kanaele(a):
    """Wertet die Kanäle aus einer Textdatei (kanaele.txt) nacheinander aus."""
    kanaele = []   # (Name, eigenes Limit oder None); Zeile: "name" oder "name 100"
    for z in open(a.datei, encoding="utf-8"):
        teile = z.split("#")[0].split()
        if teile:
            kanaele.append((teile[0], int(teile[1]) if len(teile) > 1 and teile[1].isdigit() else None))
    print(f"{len(kanaele)} Kanäle aus {a.datei}")
    for k, limit in kanaele:
        print(f"\n##### Kanal {k}" + (f" (bis zu {limit} Videos)" if limit else ""))
        b = argparse.Namespace(**vars(a))
        b.kanal = k
        if limit:
            b.max = limit
        try:
            scan_kanal(b)
        except SystemExit as e:
            print(f"  Kanal übersprungen: {e}", file=sys.stderr)


def scan_optionen(s):
    s.add_argument("--streamer")
    s.add_argument("--titel")
    s.add_argument("--twitch-id")
    s.add_argument("--versatz", type=int, default=0,
                   help="Sekunden, bei denen ein heruntergeladener Ausschnitt im Gesamtvideo beginnt")
    s.add_argument("--modus", default="randomizer")
    s.add_argument("--lang", default="eng", help="Tesseract-Sprache, bei deutschem Spieltext eng+deu")
    s.add_argument("--auch-deutsch", action="store_true", help="auch mit den deutschen Bossnamen vergleichen")
    s.add_argument("--intervall", type=int, default=30, help="Sekunden zwischen den Stichproben")
    s.add_argument("--hoehe", type=int, default=480, help="Bildhöhe bei Twitch-Adressen (kleiner = weniger Daten)")
    s.add_argument("--luecke", type=int, default=90, help="Sekunden ohne Treffer, bis ein Kampf als beendet gilt")
    s.add_argument("--schwelle", type=float, default=0.85)
    s.add_argument("--namen", default=os.path.join(HIER, "namen.json"))
    s.add_argument("--ohne-leistenpruefung", action="store_true",
                   help="auch Namen zählen, unter denen keine rote Lebensleiste liegt (z. B. bei Farbfiltern im Stream)")
    s.add_argument("--neu", action="store_true", help="schon vorhandenes Video erneut auswerten")
    s.add_argument("--kapitel", default=r"dark souls.*remastered",
                   help="nur Videoabschnitte (Twitch-Kapitel) auswerten, deren Spielname dazu passt")
    s.add_argument("--ganzes-video", action="store_true", help="Kapitel ignorieren, das ganze Video auswerten")


def ende_bestimmen(src, w, h, namen, sprache, schwelle, key, letzter, spanne=30):
    """Genaues Ende eines Kampfes: `letzter` ist ein Zeitpunkt mit Namen an der Leiste, nach `spanne`
    Sekunden war er weg. Durch Halbieren wird der letzte Zeitpunkt mit Namen auf etwa 2 s bestimmt."""
    lo, hi = letzter, letzter + spanne
    while hi - lo > 2:
        mitte = (lo + hi) / 2
        img = bild_bei(src, w, h, mitte)
        hit = finde_namen(img, namen, sprache, schwelle) if img else None
        if hit and hit["key"] == key:
            lo = mitte
        else:
            hi = mitte
    return lo


def dateiname(text):
    return re.sub(r'[<>:"/\\|?*]+', "_", text).strip(" .") or "unbekannt"


def clips(a):
    """Lädt jeden Kampf aus der Datenbank als Ausschnitt in 720p (private Sicherung, bevor Twitch das
    Video löscht). Das Ende wird dabei genau bestimmt. Schon vorhandene Dateien werden übersprungen."""
    global LEISTENPRUEFUNG
    LEISTENPRUEFUNG = True
    namen = lade_namen(a.namen)
    db = db_oeffnen(a.db)
    zeilen = db.execute("SELECT v.quelle, v.streamer, v.twitch_id, k.boss, k.platz, k.start_s, k.ende_s "
                        "FROM kaempfe k JOIN videos v ON v.id=k.video_id WHERE v.quelle LIKE 'http%' "
                        "ORDER BY v.id, k.start_s").fetchall()
    if a.streamer:
        zeilen = [z for z in zeilen if a.streamer.lower() in z[1].lower()]
    if a.boss:
        zeilen = [z for z in zeilen if norm(a.boss) in norm(z[3])]
    geplant = []
    for quelle, streamer, tid, boss, key, start, ende in zeilen:
        sek = int(start) - a.vor
        pfad = os.path.join(a.ziel, dateiname(streamer), dateiname(boss),
                            f"{dateiname(streamer)} - {dateiname(boss)} - {tid} - {hms(max(0, sek)).replace(':', '-')}.mp4")
        if not os.path.exists(pfad):
            geplant.append((quelle, streamer, tid, boss, key, start, ende, pfad))
    geplant.sort(key=lambda g: (int(g[2]) if str(g[2]).isdigit() else 0, g[5]))   # älteste Videos zuerst (Twitch löscht die zuerst)
    print(f"{len(zeilen)} Kämpfe in der Datenbank, {len(geplant)} noch ohne Clip.")
    if a.nur_planen:
        for g in geplant[:a.max or None]:
            print(f"  {g[1]:<14} {g[3]:<26} {hms(g[5])}–{hms(g[6])}  {g[2]}")
        return
    quellen = {}
    fertig = 0
    for quelle, streamer, tid, boss, key, start, ende, pfad in geplant:
        if a.max and fertig >= a.max:
            break
        os.makedirs(a.ziel, exist_ok=True)
        frei = shutil.disk_usage(a.ziel).free / 1e9
        if frei < a.min_frei:
            print(f"Nur noch {frei:.1f} GB frei auf dem Ziellaufwerk (Grenze {a.min_frei} GB), Lauf beendet.")
            break
        try:
            if quelle not in quellen:
                args = argparse.Namespace(streamer=None, titel=None, twitch_id=None, hoehe=480)
                src = quelle_aufloesen(quelle, args)[0]
                quellen[quelle] = (src,) + video_info(src)[:2]
            src, w, h = quellen[quelle]
            ende_neu = ende_bestimmen(src, w, h, namen, "eng", 0.85, key, ende)
            von, bis = max(0, int(start) - a.vor), int(ende_neu) + a.nach
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            print(f"{streamer} {boss} {hms(von)}–{hms(bis)} (Ende bestimmt: {hms(ende_neu)}, davor {hms(ende)})")
            r = subprocess.run(["yt-dlp", "-f", f"best[height<={a.hoehe}]/best", "--download-sections", f"*{von}-{bis}",
                                "-o", pfad, "--no-progress", quelle], capture_output=True, text=True)
            if r.returncode or not os.path.exists(pfad):
                print("   Fehler:", (r.stderr or r.stdout)[-300:].strip(), file=sys.stderr)
            else:
                fertig += 1
                print(f"   gespeichert: {pfad} ({os.path.getsize(pfad) / 1e6:.0f} MB)")
        except SystemExit as e:
            print(f"   übersprungen: {e}", file=sys.stderr)
    print(f"{fertig} Clips gespeichert.")


def abdeckung(a):
    """Zeigt für jeden Boss-Platz (5 Punkte), ob schon ein Kampf in der Datenbank dazu passt.
    Ein Kampf zählt für jeden Platz, den seine Deutungen nennen (bei mehrdeutigen Namen für mehrere)."""
    db = db_oeffnen(a.db)
    plaetze = [r for r in json.load(open(a.namen, encoding="utf-8")) if r["pts"] >= 5]
    zaehl = {r["key"]: [0, set()] for r in plaetze}
    for kand, tid in db.execute("SELECT k.kandidaten, v.twitch_id FROM kaempfe k JOIN videos v ON v.id=k.video_id"):
        for p in {c["platz"] for c in json.loads(kand)}:
            if p in zaehl:
                zaehl[p][0] += 1
                zaehl[p][1].add(tid)
    fehlt = 0
    for r in plaetze:
        n, v = zaehl[r["key"]][0], len(zaehl[r["key"]][1])
        fehlt += n == 0
        print(f"{'FEHLT' if n == 0 else 'ok   '}  {r['en']:<28} {r['area_de']:<28} {n} Kämpfe in {v} Videos   (dort steht: {r['rando_en']})")
    print(f"\n{len(plaetze) - fehlt} von {len(plaetze)} Boss-Plätzen haben mindestens einen Kampf.")


def bereinigen(a):
    """Entfernt Einträge von lokalen Test-Dateien (Quelle ist keine Twitch-Adresse). Sie würden sonst
    neben dem späteren Gesamtlauf desselben Videos doppelt erscheinen."""
    db = db_oeffnen(a.db)
    alt = db.execute("SELECT id, quelle FROM videos WHERE quelle NOT LIKE 'http%'").fetchall()
    for vid, q in alt:
        n = db.execute("DELETE FROM kaempfe WHERE video_id=?", (vid,)).rowcount
        db.execute("DELETE FROM videos WHERE id=?", (vid,))
        print(f"entfernt: {q} ({n} Kämpfe)")
    # Kämpfe mit Namen, die nach den aktuellen Regeln keine Bossnamen mehr sind (alte Fehltreffer)
    gueltig = set(lade_namen(os.path.join(HIER, "namen.json")))
    veraltet = [(i, b) for i, b in db.execute("SELECT id, boss FROM kaempfe") if norm(b) not in gueltig]
    for i, b in veraltet:
        db.execute("DELETE FROM kaempfe WHERE id=?", (i,))
    if veraltet:
        print(f"{len(veraltet)} Kämpfe mit nicht mehr gültigem Namen entfernt: " + ", ".join(sorted({b for _, b in veraltet})))
    db.commit()
    print(f"{len(alt)} Quellen entfernt.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=os.path.join(HIER, "daten", "archiv.db"))
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("quelle")
    scan_optionen(s)
    s.set_defaults(f=scan)
    k = sub.add_parser("scan-kanal", help="letzte Aufzeichnungen eines Twitch-Kanals auswerten")
    k.add_argument("kanal", help="Kanalname oder Adresse")
    k.add_argument("--max", type=int, default=5, help="höchstens so viele Videos (neueste zuerst)")
    k.add_argument("--titel-filter", help="nur Videos, deren Titel zu diesem Ausdruck passt (z. B. 'dldu|rando')")
    k.add_argument("--min-dauer", type=int, default=20, help="Videos unter so vielen Minuten überspringen")
    k.add_argument("--nur-liste", action="store_true", help="nur die Videoliste zeigen, nichts auswerten")
    scan_optionen(k)
    k.set_defaults(f=scan_kanal)
    ks = sub.add_parser("scan-kanaele", help="alle Kanäle aus kanaele.txt auswerten")
    ks.add_argument("--datei", default=os.path.join(HIER, "kanaele.txt"))
    ks.add_argument("--max", type=int, default=5, help="je Kanal höchstens so viele Videos (neueste zuerst)")
    ks.add_argument("--titel-filter", help="nur Videos, deren Titel zu diesem Ausdruck passt")
    ks.add_argument("--min-dauer", type=int, default=20)
    ks.add_argument("--nur-liste", action="store_true")
    scan_optionen(ks)
    ks.set_defaults(f=scan_kanaele)
    e = sub.add_parser("export")
    e.add_argument("--out", default=os.path.join(HIER, "docs", "kaempfe.json"))
    e.set_defaults(f=export)
    c = sub.add_parser("clips", help="Kämpfe als Ausschnitte in 720p sichern (private Kopie)")
    c.add_argument("--ziel", required=True, help="Zielordner, z. B. D:\\DSRClips")
    c.add_argument("--hoehe", type=int, default=720)
    c.add_argument("--vor", type=int, default=10, help="Sekunden vor dem Kampfbeginn")
    c.add_argument("--nach", type=int, default=15, help="Sekunden nach dem Verschwinden der Leiste")
    c.add_argument("--streamer", help="nur Kämpfe dieses Streamers")
    c.add_argument("--boss", help="nur Kämpfe mit diesem Namen an der Leiste")
    c.add_argument("--max", type=int, default=0, help="höchstens so viele Clips in diesem Lauf (zum Testen)")
    c.add_argument("--min-frei", type=float, default=5, help="Lauf beenden, wenn auf dem Ziellaufwerk weniger GB frei sind")
    c.add_argument("--nur-planen", action="store_true", help="nur zeigen, was geladen würde")
    c.add_argument("--namen", default=os.path.join(HIER, "namen.json"))
    c.set_defaults(f=clips)
    ab = sub.add_parser("abdeckung", help="zeigen, welche Boss-Plätze schon in der Datenbank vorkommen")
    ab.add_argument("--namen", default=os.path.join(HIER, "namen.json"))
    ab.set_defaults(f=abdeckung)
    b = sub.add_parser("bereinigen", help="Einträge von lokalen Test-Dateien entfernen")
    b.set_defaults(f=bereinigen)
    q = sub.add_parser("suche")
    q.add_argument("text")
    q.add_argument("--out", help="Ergebnis in diese Datei schreiben (UTF-8)")
    q.set_defaults(f=suche)
    for strom in (sys.stdout, sys.stderr):   # Windows-Konsole: Sonderzeichen wie → nicht abstürzen lassen
        try:
            strom.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    a = p.parse_args()
    try:
        a.f(a)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

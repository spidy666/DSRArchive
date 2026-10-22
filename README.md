# DSR-Archiv

Findet Bosskämpfe in aufgezeichneten Dark-Souls-Remastered-Randomizer-Streams und legt sie in eine Datenbank: **Streamer, Boss, Link zum Twitch-Video mit Zeitstempel** (10 Sekunden vor Kampfbeginn).

Grundlage: Im Randomizer zeigt die Lebensleiste den Namen des **Original-Platzes**, nicht den des Gegners (bisher an zwei Plätzen beobachtet: Taurus-Dämon-Platz mit Gargoyle, Mausoleumswächter-Platz mit Kalameet). Welcher Gegner im Randomizer dort steht, sagt `namen.json` (84 Plätze, aus `dsr_enemies.json` des DSR Trackers).

## Voraussetzungen
- Python 3 und Pillow: `pip install -r requirements.txt`
- `ffmpeg` und `ffprobe` im PATH
- `tesseract` im PATH (Sprachdatei `eng`). Der Spieltext der Streams ist englisch. Für deutschen Text: Sprachdatei `deu` installieren und `--lang eng+deu --auch-deutsch` angeben
- `yt-dlp` nur, wenn Twitch-Adressen direkt ausgewertet werden

## Benutzung
```
python dsrarchive.py scan "video.mp4" --streamer Name --twitch-id 1234567890
python dsrarchive.py scan "https://www.twitch.tv/videos/1234567890"
python dsrarchive.py suche gargoyle
python dsrarchive.py export
```
- Bei einer Twitch-Adresse werden Streamer, Titel und ID automatisch ermittelt (yt-dlp). Bei Dateien wird die ID aus dem Dateinamen gelesen, wenn er `[v1234567890]` enthält (so benennt yt-dlp), sonst mit `--twitch-id` angeben.
- `--versatz 12600`: Sekunde im Gesamtvideo, bei der ein heruntergeladener Ausschnitt beginnt (damit die Links stimmen).
- `--intervall 20`: Sekunden zwischen den Stichproben. Der Start eines Kampfes wird danach in 2-Sekunden-Schritten genauer bestimmt.
- Schon eingetragene Videos werden übersprungen (`--neu` wertet erneut aus).
- Die Datenbank liegt in `daten/archiv.db` (nicht im Repo). `export` schreibt `docs/kaempfe.json`, die Suchseite `docs/index.html` liest diese Datei.

## So funktioniert die Erkennung
Aus dem unteren Teil des Bildes (ab 55 % der Höhe) wird alle N Sekunden ein Bild geholt. Tesseract liest den Text mit drei Bildfiltern, der beste Treffer gegen die englischen Bossnamen (unscharfer Vergleich, auch Namensanfänge wie „Chaos Witch“) gewinnt. Es gibt keinen festen Ausschnitt, die Namensleiste wird im Bild gesucht.

## Stand und Grenzen
Getestet an künstlichen Videos (720p und 1080p), die aus drei echten Screenshots zusammengesetzt sind: alle drei Kämpfe gefunden, Startzeit auf die Sekunde. Mit echten Videos noch nicht.
- Mini-Bosse haben keine Namensleiste und werden nicht erfasst. Welche Plätze eine haben, ist noch nicht geklärt.
- Mehrere Plätze heißen gleich (Kanalisierer, Untoter Drache, Reißkeiler, Ritter von Berenike, Titanitdämon): Dann stehen alle Kandidaten im Ergebnis (`mehrdeutig`).
- Kein Siegesbanner: Auch Kämpfe, die der Spieler verliert, werden eingetragen. Ein Eintrag heißt „Boss war an der Leiste“, nicht „besiegt“.
- Mögliche Fehltreffer: Einblendungen im Bild, die Gegnernamen zeigen (z. B. die Liste des Trackers als Overlay unten im Bild), können als Treffer gelesen werden. Eine Prüfung „Leiste unter dem Namen“ fehlt noch.
- Tempo: etwa 2 Sekunden pro Stichprobe. Ein 6-Stunden-Video mit `--intervall 20` braucht rund eine halbe Stunde. Eine schnelle Vorprüfung, ob überhaupt eine Leiste im Bild ist, fehlt noch.
- Die englischen Namen in `namen.json` sind die der Tracker-Liste und können von den Spieltexten abweichen.

## Hinweise
- Twitch löscht alte Videos, Links können mit der Zeit ins Leere führen.
- Die Nutzungsbedingungen von Twitch zum Abrufen fremder Videos selbst prüfen.
- Die Treffer sind automatisch erkannt und können Fehler enthalten.

# DSR-Archiv

Findet Bosskämpfe in aufgezeichneten Dark-Souls-Remastered-Randomizer-Streams und legt sie in eine Datenbank: **Streamer, Boss, Link zum Twitch-Video mit Zeitstempel** (10 Sekunden vor Kampfbeginn).

Grundlage: Die Lebensleiste zeigt im Randomizer **nicht immer denselben Namen**. Mal steht dort der Name des Original-Platzes (Taurus-Dämon-Platz mit Gargoyle: Leiste „Taurus Demon"), mal der des Ersatz-Gegners (Asylum-Dämon-Platz mit Pinwheel: Leiste „Pinwheel"). Der Randomizer ändert den Namen bei manchen Ersetzungen mit. Eine feste Regel dafür ist nicht bekannt. Deshalb speichert das Programm den gelesenen Namen und alle möglichen Deutungen („Platz X, dort steht Y" oder „Ersatz-Gegner an Platz X"); `namen.json` (84 Plätze, aus `dsr_enemies.json` des DSR Trackers) liefert die Zuordnung.

## Voraussetzungen
- Python 3 und Pillow: `pip install -r requirements.txt`
- `ffmpeg` und `ffprobe` im PATH
- `tesseract` im PATH (Sprachdatei `eng`). Der Spieltext der Streams ist englisch. Für deutschen Text: Sprachdatei `deu` installieren und `--lang eng+deu --auch-deutsch` angeben
- `yt-dlp` nur, wenn Twitch-Adressen direkt ausgewertet werden

## Benutzung
```
python dsrarchive.py scan "video.mp4" --streamer Name --twitch-id 1234567890
python dsrarchive.py scan "https://www.twitch.tv/videos/1234567890"
python dsrarchive.py scan-kanal HollyLP --max 5 --nur-liste
python dsrarchive.py scan-kanal HollyLP --max 5 --titel-filter "dldu|rando"
python dsrarchive.py suche gargoyle
python dsrarchive.py export
```
- `scan-kanal`: holt die Liste der Aufzeichnungen eines Kanals mit yt-dlp (ohne Twitch-Zugangsdaten), neueste zuerst, und wertet sie nacheinander aus. `--max` begrenzt die Anzahl, `--titel-filter` wählt nach Titel aus (die Kategorie eines Videos liefert die Liste nicht sicher mit), `--min-dauer` (Standard 20 Minuten) überspringt kurze Videos, `--nur-liste` zeigt nur die Auswahl. Schon eingetragene Videos werden übersprungen, mit Strg+C abgebrochene Läufe behalten die fertigen Videos. Noch nicht an einem echten Kanal getestet.
- Bei einer Twitch-Adresse werden Streamer, Titel und ID automatisch ermittelt (yt-dlp). Bei Dateien wird die ID aus dem Dateinamen gelesen, wenn er `[v1234567890]` enthält (so benennt yt-dlp), sonst mit `--twitch-id` angeben.
- `--versatz 12600`: Sekunde im Gesamtvideo, bei der ein heruntergeladener Ausschnitt beginnt (damit die Links stimmen).
- `--intervall 30`: Sekunden zwischen den Stichproben (Standard 30). Der Start eines Kampfes wird danach durch Halbieren des Zeitfensters auf etwa 2 Sekunden genau bestimmt.
- `--hoehe 480`: Bildhöhe, die bei Twitch-Adressen geladen wird (Standard 480p, deutlich weniger Daten als 720p).
- Schon eingetragene Videos werden übersprungen (`--neu` wertet erneut aus).
- Die Datenbank liegt in `daten/archiv.db` (nicht im Repo). `export` schreibt `docs/kaempfe.json`, die Suchseite `docs/index.html` liest diese Datei.

## So funktioniert die Erkennung
Aus dem unteren Teil des Bildes (ab 55 % der Höhe) wird alle N Sekunden ein Bild geholt. Tesseract liest den Text mit drei Bildfiltern, der beste Treffer gegen die englischen Bossnamen (unscharfer Vergleich, auch Namensanfänge wie „Chaos Witch“) gewinnt. Es gibt keinen festen Ausschnitt, die Namensleiste wird im Bild gesucht.

## Stand und Grenzen
Getestet an künstlichen Videos aus drei Screenshots (alle drei Kämpfe gefunden) und an einem echten Twitch-Clip (Seath-Kampf, 720p und 480p, Abstände von 15 bis 60 Sekunden: immer gefunden, Start auf etwa 3 Sekunden genau). Trefferquote pro Bild im Kampf: 96 % bei 720p, 93 % bei 480p, keine Fehltreffer auf 18 Bildern ohne Boss. Das ist nur ein Boss und ein Streamer, mehr Material fehlt noch.
- Mini-Bosse haben keine Namensleiste und werden nicht erfasst. Welche Plätze eine haben, ist noch nicht geklärt.
- Mehrere Plätze heißen gleich (Kanalisierer, Untoter Drache, Reißkeiler, Ritter von Berenike, Titanitdämon): Dann stehen alle Kandidaten im Ergebnis. Dasselbe gilt für Namen, die zugleich Ersatz-Gegner an anderen Plätzen sind (Pinwheel steht auch am Asylum-Dämon- und am Mondlicht-Schmetterling-Platz).
- Kein Siegesbanner: Auch Kämpfe, die der Spieler verliert, werden eingetragen. Ein Eintrag heißt „Boss war an der Leiste“, nicht „besiegt“.
- Fehltreffer durch Text im Bild: Namen im Chat, im Inventar oder in Overlays wurden als Bossleiste gelesen (an einem 6-Stunden-Video bei 3 von 15 Einträgen belegt: Chat „ceaseless disharge" und „silver knight", Inventartext „Soul of Knight Artorias"). Seitdem zählt ein Name nur, wenn darunter ein rotes Band (die Lebensleiste) liegt: eine zusammenhängende rote Strecke von mindestens 3 % der Bildbreite, die am linken Namensrand beginnt. Eine fast leere Leiste zählt weiterhin (erste Fassung verlangte 50 % des Fensters und verlor so Sif im letzten Drittel des Kampfes). Geprüft an sieben Screenshots (vier echte Leisten angenommen, drei Chat/Inventar abgelehnt) und drei Clips; bei Farbfiltern im Stream kann es echte Leisten verwerfen (`--ohne-leistenpruefung`).
- Tempo (gemessen an einem echten 4-Minuten-Clip, auf 6 Stunden hochgerechnet): nur Schlüsselbilder werden dekodiert (etwa 10-mal schneller), nach dem ersten Treffer wird nur noch ein Streifen um die Namensposition gelesen. Das ergibt grob 6 bis 9 Minuten pro 6-Stunden-Datei bei 30 Sekunden Abstand, ohne die Zeit für den Download. Das ist eine Schätzung, kein Messwert an einer ganzen Datei.
- Die englischen Namen in `namen.json` sind die der Tracker-Liste und können von den Spieltexten abweichen.

## Hinweise
- Twitch löscht alte Videos, Links können mit der Zeit ins Leere führen.
- Die Nutzungsbedingungen von Twitch zum Abrufen fremder Videos selbst prüfen.
- Die Treffer sind automatisch erkannt und können Fehler enthalten.

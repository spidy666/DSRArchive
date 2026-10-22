# Übergabe DSR-Archiv (Stand 22.10.2026)

Für eine neue Sitzung. Zuerst `README.md` und `dsrarchive.py` lesen. Antworten auf Deutsch, nicht voreilig schließen, im Zweifelsfall nachfragen (Preference von Matthias).

## Entscheidungen von Matthias
- Repo privat, keine Lizenz. Alle Videos sind Randomizer-Runs. Link 10 Sekunden vor Kampfbeginn.
- Erst einzelne Videos von Hand verlinken, später ggf. ganze Kanäle (Twitch-API, eigene App, Schlüssel bleiben bei ihm).
- Videos lädt ein anderes Tool herunter oder `yt-dlp -g` liefert die Adresse. Ordner auf seinem PC: `C:\Users\matth\Documents\1_DSRArchive`.
- Die Sitzung läuft in einer Linux-Umgebung ohne Zugriff auf Twitch; Windows-Programme laufen nicht dort. Ausführen auf seinem PC macht er selbst.

## Stand
- `dsrarchive.py`: `scan` (Datei oder Adresse, Stichproben, Leistensuche, Startzeit verfeinern), `export`, `suche`; SQLite `daten/archiv.db`; Suchseite `docs/index.html` liest `docs/kaempfe.json`.
- Getestet an künstlichen 720p/1080p-Videos aus drei Original-Screenshots (Taurus Demon, Pinwheel, Chaos Witch Quelaag): 3 von 3 Kämpfen, Start auf die Sekunde. Mit echten Videos noch nicht.

## Offen
1. Unbeschnittene Frames/Testvideo von Matthias (mehrere Streamer, deutscher Text) in `1_DSRArchive`; Sprachdatei `deu` testen.
2. Welche Plätze haben eine Namensleiste (Mini-Bosse nicht). Nicht raten.
3. Fehltreffer durch Overlays mit Gegnernamen: Prüfung „Leiste unter dem Namen“ ergänzen.
4. Siegesbanner als „besiegt“. Schnelle Vorprüfung auf Leiste im Bild (Tempo, etwa 2 s je Stichprobe).
5. Kanalabfrage per Twitch-API (Videos je Kanal, Kategorie über die Texterkennung bestätigen).
6. Nebenspur: Transkript des Boss-Erklärvideos (Whisper) lesen und Fragen beantworten.
7. Twitch-Bedingungen für das Abrufen fremder Videos prüft Matthias selbst; Streamer-Namen vor einer Veröffentlichung klären.

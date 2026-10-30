# Changelog

Alle nennenswerten Änderungen am DSR-Archiv stehen in dieser Datei.

Das Format orientiert sich an [Keep a Changelog 1.1.0](https://keepachangelog.com/de/1.1.0/).
Das Projekt hat keine Versionsnummern (es gibt keine Tags oder Releases), deshalb sind die
Abschnitte nach Datum geordnet, der neueste zuerst.

## [Unveröffentlicht]

### Hinzugefügt
- Uhrzeit: neue Spalte `videos.stream_start` (Beginn des Videos, UTC). Neue Scans speichern sie, der Befehl
  `uhrzeiten-nachtragen` ergänzt bestehende Videos. `export` liefert `stream_start` und `kampf_beginn`,
  die Suchseite zeigt Datum und Uhrzeit in der Ortszeit des Besuchers, `suche` in der Zeitzone des Rechners.
- Clip-Verknüpfung: neue Spalte `kaempfe.clip` und Befehl `clips-verknuepfen`. Der Pfad bleibt lokal
  (`suche` zeigt ihn), er steht nicht im Export und nicht auf der öffentlichen Seite.
- `uebersicht`: schreibt eine lokale `index.html` in den Clip-Ordner (Suche wie auf der öffentlichen Seite,
  dazu ein Link „Clip lokal"). Die Daten stehen in der Datei, sie braucht weder Netz noch Twitch.
- Tests für Zeitstempel, Spaltenmigration, Export ohne Clip-Pfad und Clip-Verknüpfung und Übersicht.
- `tools/transkribieren.py`: transkribiert ein Video lokal mit faster-whisper auf der CPU und schreibt
  `.srt` und `.txt` (`--sprache`, `--modell`, `--ohne-vad`). `--fortsetzen` setzt ein abgebrochenes
  Transkript am Stand der `.srt` fort. Das Audio wird über ffmpeg dekodiert.

## [2026-10-29]

### Hinzugefügt
- Änderungsprotokoll `CHANGELOG.md`.
- `clips`: `start_bestimmen` misst den Kampfbeginn vor dem Download am Video nach
  (rückwärts in 4-s-Schritten, höchstens 30 s, Lücken bis 16 s gelten als Fortsetzung).

### Geändert
- `clips`: `ende_bestimmen` arbeitet jetzt vorwärts in 4-s-Schritten (statt Halbieren) und wird nie
  früher als der gespeicherte Wert, damit der Kampf ganz im Clip ist.
- `clips`: vergleicht auch die deutschen Bossnamen.
- `docs/kaempfe.json` mit den korrigierten Kampfzeiten neu exportiert (853 Kämpfe in 94 Videos).
- `README.md` und `UEBERGABE.md` auf den Endstand gebracht (Python 3.12, Zeitkorrektur, Clips).

### Behoben
- `clips`: Der Vergleich in der Bestimmung von Start und Ende benutzte den Platzschlüssel statt des
  Namensschlüssels und fand nie einen Treffer. „Ende bestimmt" war deshalb immer nur der Datenbankwert.

## [2026-10-27]

### Hinzugefügt
- Befehl `zeiten-korrigieren` (`--nur-zeigen` ändert nichts): zieht bei bereits gescannten Videos die
  Startzeit des Streams von allen Kampfzeiten ab. Korrigierte Videos werden in `videos.zeit_korrigiert`
  markiert und nicht doppelt korrigiert.
- Test für die Bildzeiten bei Streams, die nicht bei Sekunde 0 beginnen.

### Behoben
- Zeitversatz: Twitch-VODs beginnen laut ffprobe (`start_time`) nicht bei 0, sondern bei etwa 62 bis 66 s.
  Der Scan las mit `-copyts` die Rohzeiten, alle Kampfzeiten und Links lagen deshalb um diesen Wert zu spät.
  Neue Scans ziehen die Startzeit ab.

## [2026-10-25]

### Hinzugefügt
- Öffentliche Suchseite auf GitHub Pages (<https://spidy666.github.io/DSRArchive/>) mit Freitextsuche,
  Filtern für Streamer, Boss und Gebiet, Sortierung und Seitenaufbau; `docs/kaempfe.json` mit 853 Kämpfen.
- Offline-Tests (`tests/`) und GitHub-Actions-Workflow für Windows (Python 3.12).
- Prüfung der ffprobe-Metadaten (Auflösung, Dauer) mit verständlichen Fehlermeldungen.

### Geändert
- Zeitlimits und Fehlerbehandlung für ffmpeg, ffprobe und Tesseract; Startfehler der Programme werden
  als lesbare Fehlermeldung ausgegeben, die Programmzeile bricht ohne Traceback ab.
- Datenbankzugriffe: `scan --neu` ersetzt Video und Kämpfe in einer Transaktion, `bereinigen` mit Rollback,
  Lesebefehle (`suche`, `export`, `abdeckung`, `clips`) öffnen die Datenbank nur lesend.
- Lava-Szenen (Dämonenruinen): bekannte Treffer zählen als anwesend, Pause 45 s, ein nicht getrennter Kampf
  behält sein bisheriges Ende.

## [2026-10-24]

### Geändert
- Versuche trennen: Das Ende kommt aus der Leistenprüfung, das Fenster reicht bis 35 s hinter den letzten Treffer.
- Bei rotem Hintergrund (Lava) zählt für die Anwesenheit nur der Name, die Farbprüfung taugt dort nicht.

### Behoben
- Negative und null Sekunden lange Kämpfe: Einzeltreffer enden mindestens 2,5 s nach dem Start,
  `bereinigen` korrigiert vorhandene Einträge.
- Inventar- und Menütexte mit orangefarbener Markierung (zum Beispiel „Core of an Iron Golem") wurden als
  Leiste gewertet; bei rotem Hintergrund werden Namen ab 30 % Bildbreite von links nicht mehr als Leiste gezählt.

## [2026-10-23]

### Hinzugefügt
- `clips`: Kämpfe als 720p-Ausschnitte sichern (private Sicherung), älteste Videos zuerst, Stopp bei zu wenig
  freiem Platz.
- `abdeckung`: zeigt, welche Boss-Plätze schon Kämpfe haben.
- `--belege`: Belegbild und gelesener Text für jeden Einzeltreffer.
- Versuche trennen: Das Kampfende wird genau bestimmt und das Kampffenster alle 5 s geprüft; nach 20 s ohne
  Leiste oder Namen beginnt ein neuer Versuch mit eigenem Eintrag und Link (`--versuchspause`,
  `--ohne-versuche`).
- Datum des Videos in der Datenbank, in `suche`, `export` und auf der Suchseite (sortierbare Spalte).
- Feste Alias-Tabelle (Gargoyle = Bell Gargoyle, weil die Webcam das „Bell" verdeckt).
- `kanaele.txt` mit eigenem Limit pro Kanal.

### Geändert
- `bereinigen` entfernt auch Kämpfe mit nicht mehr gültigem Bossnamen.
- Mini-Boss-Plätze (3 Punkte) zählen nicht mehr als Platzname, nur als Ersatz, wenn dort ein echter Boss steht.
- `suche --out` schreibt UTF-8, die Konsole wird auf UTF-8 gestellt.
- Belegbilder in höherer JPEG-Qualität.

### Behoben
- Fehltreffer durch Chat bei rotem Hintergrund und durch Namen in Listen und Notizen
  (Text direkt über und unter dem Namen).

## [2026-10-22]

### Hinzugefügt
- Erster Stand: Erkennung der Bossleiste per Tesseract, SQLite-Datenbank, `export` und `suche`, Suchseite
  `docs/index.html`.
- `--versatz` für heruntergeladene Ausschnitte.
- Speichern aller Deutungen eines Leistennamens (Platz oder Ersatz-Gegner).
- Prüfung, dass unter dem Namen eine rote Lebensleiste liegt (auch fast leer).
- Zusammenführen von Kämpfen am gleichen Platz, volle Suche und Zählung aller Treffer im Kampf.
- `scan-kanal` und `scan-kanaele` (Kanalliste in `kanaele.txt`), `--nur-liste`.
- Nur Dark-Souls-Remastered-Abschnitte laut Twitch-Kapiteln werden ausgewertet (`--kapitel`, `--ganzes-video`).
- Befehl `bereinigen` für Einträge lokaler Test-Dateien.

### Geändert
- Standardmäßig nur englische Bossnamen vergleichen (`--auch-deutsch` für zusätzliche deutsche Namen).
- Schneller und robuster: Schlüsselbilder, Namensstreifen, bessere Bildfilter.
- Strg+C stoppt auch `scan-kanaele` komplett.

### Behoben
- Namensposition verfiel nach Kampfende nicht, deshalb wurden neue Bosse an anderer Stelle übersehen.
- Fast leere Leisten (zum Beispiel bei Sif) wurden verworfen.
- „Bell Gargoyle" (Einzahl) als Leistenname, der längere Namenstreffer gewinnt bei fast gleichem Wert.

[Unveröffentlicht]: https://github.com/spidy666/DSRArchive/compare/6f7a49f...HEAD

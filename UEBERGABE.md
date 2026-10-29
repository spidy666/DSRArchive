# Übergabe DSR-Archiv (Stand 29.10.2026)

Für eine neue Sitzung. Zuerst `README.md` und `dsrarchive.py` lesen. Antworten auf Deutsch, nicht voreilig schließen, im Zweifelsfall nachfragen (Preference von Matthias).

## Entscheidungen von Matthias
- Repo privat, keine Lizenz. Alle Videos sind Randomizer-Runs. Link 10 Sekunden vor Kampfbeginn.
- Erst einzelne Videos von Hand verlinken, später ggf. ganze Kanäle (Twitch-API, eigene App, Schlüssel bleiben bei ihm).
- Videos lädt ein anderes Tool herunter oder `yt-dlp -g` liefert die Adresse. Ordner auf seinem PC: `C:\Users\matth\Documents\1_DSRArchive`.
- Die Sitzung läuft in einer Linux-Umgebung ohne Zugriff auf Twitch; Windows-Programme laufen nicht dort. Ausführen auf seinem PC macht er selbst.

## Stand
- Wichtig (von Matthias bestätigt): Der Randomizer ändert bei manchen Ersetzungen den Namen an der Leiste mit. Beobachtet: Taurus-Dämon-Platz → Leiste „Taurus Demon", Gegner Gargoyle; Asylum-Dämon-Platz → Leiste „Pinwheel", Gegner Pinwheel. Das Programm speichert den gelesenen Namen und alle Deutungen (Platz oder Ersatz-Gegner). Regel dafür offen, nach ihr fragen bzw. aus mehr Daten ableiten.
- `dsrarchive.py`: `scan` (Datei oder Adresse, Stichproben, Leistensuche, Startzeit verfeinern), `export`, `suche`; SQLite `daten/archiv.db`; Suchseite `docs/index.html` liest `docs/kaempfe.json`.
- Echter Test am 22.10.: Twitch-Video 2906825248 (KNiSTER), Ausschnitt ab 3:30:00, 720p: Seath-Platz erkannt (→ Ritter Artorias), Start 3:31:34, keine Fehltreffer. Zweiter Test: LillyTheChilly 2906737076, Ausschnitt ab 1:02:00: Pinwheel-Kampf ab 1:04:24 gefunden, sonst keine Kämpfe im Ausschnitt (laut Matthias ist dort sonst kein Boss).
- Getestet außerdem an künstlichen 720p/1080p-Videos aus drei Original-Screenshots (Taurus Demon, Pinwheel, Chaos Witch Quelaag): 3 von 3 Kämpfen, Start auf die Sekunde. Mit echten Videos noch nicht.

## Offen
1. Weitere echte Videos testen (mehrere Streamer, mehrere Kämpfe in einem Video). Der Spieltext der Streams ist laut Matthias einheitlich englisch, `deu` wird nicht gebraucht.
2. Welche Plätze haben eine Namensleiste (Mini-Bosse nicht). Nicht raten.
3. Fehltreffer durch Overlays mit Gegnernamen: Prüfung „Leiste unter dem Namen“ ergänzen.
4. Siegesbanner als „besiegt“. Schnelle Vorprüfung auf Leiste im Bild (Tempo, etwa 2 s je Stichprobe).
5. Kanalabfrage per Twitch-API (Videos je Kanal, Kategorie über die Texterkennung bestätigen).
6. Nebenspur: Transkript des Boss-Erklärvideos (Whisper) lesen und Fragen beantworten.
7. Twitch-Bedingungen für das Abrufen fremder Videos prüft Matthias selbst; Streamer-Namen vor einer Veröffentlichung klären.

## Stand 22.10.2026: Test am 6-Stunden-Video (H0llyLP, 2905111020)
Gesamtlauf 341 s (480p, Abstand 30 s), 12 Kämpfe. Am Video geprüft: Bell Gargoyle (1:07:41), Iron Golem (4:01:39 Beginn, 4:03:54 zweiter Abschnitt nach 114 s Lücke), Ornstein und Smough (4:41:58, Smough ist Teil desselben Kampfes), Sif (5:19:16), Ceaseless Discharge (5:33:30).
Behobene Fehler: Leistenprüfung verlor Sif bei fast leerer Leiste (jetzt zusammenhängende rote Strecke ab 3 % der Breite, Beginn am Namensrand); Namensposition verfiel nie, dadurch wurde Sif im Gesamtlauf übersehen; Teilname „Gargoyle" schlug „Bell Gargoyle".
Offen: Ende/Sieg (leere Leiste = besiegt), Mini-Bosse ohne Namensleiste, Deutung Platz oder Ersatz aus Reihenfolge, Kanalliste per Twitch-API, `export` und GitHub Pages (privates Repo), Flüstern-Transkript (Whisper) des Bosslagen-Videos.

## Endstand 29.10.2026 (das Event ist vorbei, keine neuen Streams mehr)
- Alle 14 Kanäle aus `kanaele.txt` (edopeh wieder eingeschaltet) ausgewertet: **853 Kämpfe in 94 Videos**, alle 26 Boss-Plätze belegt (dünn: Kalameet, Artorias, Manus je 3, Bed of Chaos und Priscilla je 4; die Runs kommen dort selten an, laut Matthias fehlen keine Videos).
- **Zeitversatz behoben (27.10.):** Twitch-VODs haben `start_time` 62 bis 66 s, der Scan las Rohzeiten (`-copyts`). Neue Scans ziehen den Wert ab, alte Einträge wurden mit `zeiten-korrigieren` korrigiert, Sicherungskopie `daten/archiv_vor_zeitkorrektur.db`. Am Player geprüft.
- **Clips:** alle 853 Kämpfe liegen als 720p-Ausschnitte in `D:\DSRClips` (privat, nicht veröffentlichen). Start und Ende werden beim Download am Video nachgemessen. Dabei wurde ein Fehler im Vergleich (Platz- statt Namensschlüssel) behoben.
- **Webseite:** `docs/kaempfe.json` (853 Einträge, korrigierte Zeiten) auf GitHub Pages veröffentlicht, Repo ist öffentlich.
- **Entscheidungen von Matthias:** Keine feste Regel Name = Platz oder Ersatz (Bosse wurden im Event ausgetauscht). Die Leiste zählt mit dem Namen und den wahrscheinlichen Deutungen, falsche Vermutungen sind in Ordnung. Das Spiel läuft bei manchen Streamern auf Deutsch; ein Test (Knister 2900576310 mit `--auch-deutsch`) ergab dieselben 9 Kämpfe, einen kompletten Neuscan hielten wir nicht für nötig. Neue Streams kommen nicht dazu.
- **Offen (optional):** Lava-Kämpfe in den Dämonenruinen können mehrere Versuche enthalten (Knister 2902335169 Firesage 276 s, 2900576310 Ceaseless 247 s); Einzeltreffer haben nur eine Untergrenze (Start bis etwa 20 s ungenau); kein Siegesbanner (Einträge heißen „Boss an der Leiste", nicht „besiegt"); Mini-Bosse ohne Leiste fehlen; Streamer-Namen auf der öffentlichen Seite sichtbar (Entscheidung von Matthias); Nebenspuren: Whisper-Transkript des Boss-Erklärvideos, VirusTotal-Link für den DSR Tracker.
- Python auf dem PC: 3.12 (py -3.12), yt-dlp und Pillow dort installiert, Pfad vorn im Benutzer-PATH.

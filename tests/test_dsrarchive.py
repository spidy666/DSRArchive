"""Offline-Tests für deterministische Hilfsfunktionen aus dsrarchive.py."""
import contextlib
import io
import unittest
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import dsrarchive


class NormalisierungUndNamensvergleich(unittest.TestCase):
    def test_norm_vereinheitlicht_akzente_und_zeichen(self):
        self.assertEqual(dsrarchive.norm("  Quelaág, Lord! "), "quelaag lord")

    def test_vergleiche_findet_exakten_namen_ohne_unnoetige_abwertung(self):
        name, score = dsrarchive.vergleiche("Bell Gargoyle", {"bell gargoyle"}, 0.85)
        self.assertEqual(name, "bell gargoyle")
        self.assertEqual(score, 1.0)

    def test_vergleiche_erkennt_mehrwortigen_namensanfang(self):
        name, score = dsrarchive.vergleiche("Chaos Witch", {"chaos witch quelaag"}, 0.85)
        self.assertEqual(name, "chaos witch quelaag")
        self.assertGreaterEqual(score, 0.85)

    def test_vergleiche_verwirft_zu_kurzen_text(self):
        self.assertEqual(dsrarchive.vergleiche("Sif", {"great grey wolf sif"}, 0.85), (None, 0))


class TrefferGruppierung(unittest.TestCase):
    @staticmethod
    def treffer(key, zeit, score=0.9):
        return (int(zeit), zeit, {
            "key": key,
            "name": key,
            "kandidaten": [],
            "score": score,
            "text": key,
            "box": [1, 2, 3, 4],
        })

    def test_nahe_treffer_des_selben_bosses_werden_ein_kampf(self):
        kaempfe = dsrarchive.gruppiere(
            [self.treffer("sif", 10), self.treffer("sif", 30)], 25
        )
        self.assertEqual(len(kaempfe), 1)
        self.assertEqual((kaempfe[0]["start"], kaempfe[0]["ende"]), (10, 30))
        self.assertEqual(kaempfe[0]["treffer"], 2)

    def test_grosse_luecke_oder_andere_bosse_trennen_kaempfe(self):
        kaempfe = dsrarchive.gruppiere(
            [self.treffer("sif", 10), self.treffer("sif", 50), self.treffer("nito", 55)], 25
        )
        self.assertEqual([k["key"] for k in kaempfe], ["sif", "sif", "nito"])


class LavaVersuchstrennung(unittest.TestCase):
    @staticmethod
    def kampf(ende):
        return {
            "key": "capra",
            "keys": {"capra"},
            "start": 100,
            "ende": ende,
            "box": [100, 100, 120, 20],
        }

    @staticmethod
    def treffer(zeit):
        return (int(zeit), zeit, {"key": "capra"})

    def auswerten(self, kampf, zeiten, treffer):
        bildklasse = type("BildStub", (), {"size": (1920, 1080)})
        bilder = [bildklasse() for _ in zeiten]

        def fake_bilder(*args):
            args[4].extend(zeiten)
            yield from bilder

        def rote_szene(_img, _box, info):
            info["gesaettigt"] = True
            return False

        with patch.object(dsrarchive, "bilder", side_effect=fake_bilder), \
             patch.object(dsrarchive, "hat_leiste", side_effect=rote_szene), \
             patch.object(dsrarchive, "suche_mit_streifen", return_value=None):
            return dsrarchive.versuche_trennen(
                kampf, "video.mp4", 1920, 1080, {}, "eng", 0.85,
                treffer, True,
            )

    def test_einzelkampf_in_roter_szene_bewahrt_bisheriges_ende(self):
        kaempfe = self.auswerten(
            self.kampf(125), [100, 105, 110],
            [self.treffer(100), self.treffer(105), self.treffer(110)],
        )
        self.assertEqual(len(kaempfe), 1)
        self.assertEqual(kaempfe[0]["ende"], 125)

    def test_rote_szene_trennt_nach_mindestens_45_sekunden_abwesenheit(self):
        kaempfe = self.auswerten(
            self.kampf(160), [100, 105, 150, 155],
            [self.treffer(100), self.treffer(105), self.treffer(155)],
        )
        self.assertEqual(len(kaempfe), 2)
        self.assertEqual([k["versuch"] for k in kaempfe], [1, 2])
        self.assertEqual([k["versuche"] for k in kaempfe], [2, 2])


class TwitchHilfsfunktionen(unittest.TestCase):
    def test_liste_parsen_baut_video_url_aus_id(self):
        daten = dsrarchive.liste_parsen(
            '{"entries":[{"id":"v123456","title":"Run","duration":90}]}'
        )
        self.assertEqual(daten, [{
            "url": "https://www.twitch.tv/videos/123456",
            "titel": "Run",
            "dauer": 90,
        }])

    def test_spiel_abschnitte_schneidet_auf_videodauer_und_filtert_kurze(self):
        kapitel = [
            {"start_time": 10, "end_time": 100, "title": "Dark Souls Remastered"},
            {"start_time": 100, "end_time": 130, "title": "Dark Souls Remastered"},
            {"start_time": 130, "end_time": 200, "title": "Other game"},
        ]
        self.assertEqual(
            dsrarchive.spiel_abschnitte(kapitel, "dark souls.*remastered", 150),
            [(10, 100)],
        )

    def test_zeit_link_begrenzt_negative_zeit_auf_null(self):
        self.assertEqual(
            dsrarchive.zeit_link("123456", -8),
            "https://www.twitch.tv/videos/123456?t=0h0m0s",
        )


class ExterneWerkzeugeUndTransaktionen(unittest.TestCase):
    def test_externer_prozessfehler_wird_mit_stderr_weitergegeben(self):
        result = type("Result", (), {"returncode": 2, "stderr": "kaputtes Video"})()
        with patch.object(dsrarchive.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "kaputtes Video"):
                dsrarchive._run_checked(["ffprobe"], "ffprobe", 10)

    def test_timeout_wird_als_verstaendlicher_fehler_gemeldet(self):
        timeout = dsrarchive.subprocess.TimeoutExpired(["tesseract"], 60)
        with patch.object(dsrarchive.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "Zeitlimit von 60 s"):
                dsrarchive._run_checked(["tesseract"], "Tesseract", 60)

    def test_cli_zeigt_werkzeugfehler_ohne_traceback(self):
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["dsrarchive.py", "scan", "video.mp4"]), \
             patch.object(dsrarchive, "scan", side_effect=RuntimeError("ffprobe: Datei fehlt")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                dsrarchive.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertIn("Fehler: ffprobe: Datei fehlt", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_scanfehler_rollt_ersetzen_des_bisherigen_eintrags_zurueck(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "archiv.db")
            db = dsrarchive.db_oeffnen(db_path)
            cur = db.execute(
                "INSERT INTO videos(quelle,streamer) VALUES(?,?)", ("local.mp4", "alt")
            )
            video_id = cur.lastrowid
            db.execute(
                "INSERT INTO kaempfe(video_id,boss) VALUES(?,?)", (video_id, "alter Kampf")
            )
            db.commit()
            db.close()

            kandidat = {
                "gebiet": "Gebiet",
                "deutung": "ersatz",
                "anzeige": "Boss",
                "rando_en": "Boss",
                "nicht_serialisierbar": object(),
            }
            kampf = {
                "kandidaten": [kandidat], "name": "Boss", "key": "boss",
                "start": 10, "ende": 20, "score": 1.0, "treffer": 2,
            }
            with self.assertRaises(TypeError):
                dsrarchive.scan_speichern(
                    db_path, "local.mp4", (video_id,), "neu", "Titel", None,
                    100, None, "randomizer", [kampf],
                )

            db = sqlite3.connect(db_path)
            self.assertEqual(db.execute("SELECT streamer FROM videos").fetchall(), [("alt",)])
            self.assertEqual(db.execute("SELECT boss FROM kaempfe").fetchall(), [("alter Kampf",)])
            db.close()

    def test_leseverbindung_migriert_kein_altes_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "alt.db")
            db = sqlite3.connect(db_path)
            db.executescript(
                "CREATE TABLE videos(id INTEGER PRIMARY KEY, streamer TEXT, titel TEXT, "
                "twitch_id TEXT, modus TEXT);"
                "CREATE TABLE kaempfe(id INTEGER PRIMARY KEY, video_id INTEGER, boss TEXT, "
                "gebiet TEXT, rando_de TEXT, rando_en TEXT, start_s REAL, konfidenz REAL, "
                "kandidaten TEXT, ende_s REAL, treffer INTEGER);"
            )
            db.commit()
            db.close()

            db = dsrarchive.db_lesen(db_path)
            try:
                self.assertEqual(dsrarchive.zeilen_aus_db(db), [])
                spalten = {r[1] for r in db.execute("PRAGMA table_info(videos)")}
                self.assertNotIn("datum", spalten)
            finally:
                db.close()

    def test_leseverbindung_erzeugt_keine_fehlende_datenbank(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "fehlt.db")
            with self.assertRaises(sqlite3.OperationalError):
                dsrarchive.db_lesen(db_path)
            self.assertFalse(Path(db_path).exists())


if __name__ == "__main__":
    unittest.main()

"""Transkribiert eine Audio- oder Videodatei mit faster-whisper (läuft auf dem Prozessor).

Schreibt neben die Datei eine .srt (mit Zeitstempeln) und eine .txt (Text mit Zeit in H:MM:SS am Zeilenanfang).
Aufruf:  python tools/transkribieren.py "D:\\DSRClips\\_Erklaerung\\video.mp4" --sprache de --modell small
Voraussetzung:  pip install faster-whisper   (das Sprachmodell wird beim ersten Lauf automatisch geladen)
"""
import argparse
import os
import sys
import time


def hms(s):
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def srt_zeit(s):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def audio_laden(pfad):
    """Dekodiert die Datei mit ffmpeg zu 16-kHz-Mono-Daten. Das umgeht faster-whisper/PyAV: dessen eigene
    Dekodierung scheitert mit neuen av-Versionen (open() got an unexpected keyword argument 'metadata_errors')."""
    import subprocess
    import numpy as np
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", pfad, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                           capture_output=True)
    except FileNotFoundError:
        sys.exit("ffmpeg nicht gefunden (muss im PATH liegen).")
    if r.returncode or not r.stdout:
        sys.exit("ffmpeg konnte das Audio nicht lesen: " + r.stderr.decode("utf-8", "replace")[-500:])
    return np.frombuffer(r.stdout, dtype=np.float32)


def letzter_stand(pfad):
    """Nummer und Ende (s) des letzten vollständigen Eintrags einer vorhandenen .srt (0, 0.0 wenn keine)."""
    if not os.path.exists(pfad):
        return 0, 0.0
    nr, ende = 0, 0.0
    with open(pfad, encoding="utf-8") as f:
        bloecke = f.read().split("\n\n")
    for b in bloecke:
        zeilen = b.strip().splitlines()
        if len(zeilen) >= 3 and zeilen[0].isdigit() and " --> " in zeilen[1]:
            try:
                h, m, rest = zeilen[1].split(" --> ")[1].split(":")
                sek, ms = rest.split(",")
                nr, ende = int(zeilen[0]), int(h) * 3600 + int(m) * 60 + int(sek) + int(ms) / 1000
            except ValueError:
                break
    return nr, ende


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datei")
    p.add_argument("--sprache", default="de", help="Sprache des Videos (Standard de)")
    p.add_argument("--modell", default="small", help="tiny, base, small, medium oder large-v3 (größer = genauer und langsamer)")
    p.add_argument("--ohne-vad", action="store_true", help="Stille nicht überspringen")
    p.add_argument("--fortsetzen", action="store_true",
                   help="an eine abgebrochene .srt/.txt anhängen und hinter dem letzten Eintrag weitermachen")
    a = p.parse_args()
    if not os.path.exists(a.datei):
        sys.exit(f"Datei nicht gefunden: {a.datei}")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper fehlt: pip install faster-whisper")
    basis = os.path.splitext(a.datei)[0]
    print(f"Lade Modell {a.modell} ...", flush=True)
    modell = WhisperModel(a.modell, device="cpu", compute_type="int8")
    nr0, ab = letzter_stand(basis + ".srt") if a.fortsetzen else (0, 0.0)
    if a.fortsetzen:
        print(f"Setze fort ab {hms(ab)} (Eintrag {nr0 + 1}).", flush=True)
    if a.fortsetzen and nr0:   # angefangenen letzten Eintrag abschneiden, damit nichts doppelt oder halb dasteht
        with open(basis + ".srt", encoding="utf-8") as f:
            bloecke = [b for b in f.read().split("\n\n") if b.strip()][:nr0]
        with open(basis + ".srt", "w", encoding="utf-8") as f:
            f.write("\n\n".join(bloecke) + "\n\n")
        if os.path.exists(basis + ".txt"):
            with open(basis + ".txt", encoding="utf-8") as f:
                zeilen = f.read().splitlines()[:nr0]
            with open(basis + ".txt", "w", encoding="utf-8") as f:
                f.write("\n".join(zeilen) + "\n")
    optionen = {"clip_timestamps": [ab]} if ab > 0 else {}   # Zeiten bleiben die des ganzen Videos
    print("Lese Audio ...", flush=True)
    audio = audio_laden(a.datei)
    segmente, info = modell.transcribe(audio, language=a.sprache, vad_filter=not a.ohne_vad,
                                       beam_size=5, condition_on_previous_text=False, **optionen)
    dauer = info.duration or 0
    t0 = time.time()
    modus = "a" if a.fortsetzen and nr0 else "w"
    with open(basis + ".srt", modus, encoding="utf-8") as srt, open(basis + ".txt", modus, encoding="utf-8") as txt:
        for i, s in enumerate(segmente, nr0 + 1):
            text = s.text.strip()
            srt.write(f"{i}\n{srt_zeit(s.start)} --> {srt_zeit(s.end)}\n{text}\n\n")
            txt.write(f"[{hms(s.start)}] {text}\n")
            srt.flush()
            txt.flush()
            if i % 20 == 0 and dauer:
                print(f"  {hms(s.end)} von {hms(dauer)} ({s.end / dauer:.0%}), {hms(time.time() - t0)} vergangen", flush=True)
    print(f"Fertig in {hms(time.time() - t0)}:\n  {basis}.srt\n  {basis}.txt")


if __name__ == "__main__":
    main()

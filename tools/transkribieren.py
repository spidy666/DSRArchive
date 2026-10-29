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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("datei")
    p.add_argument("--sprache", default="de", help="Sprache des Videos (Standard de)")
    p.add_argument("--modell", default="small", help="tiny, base, small, medium oder large-v3 (größer = genauer und langsamer)")
    p.add_argument("--ohne-vad", action="store_true", help="Stille nicht überspringen")
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
    segmente, info = modell.transcribe(a.datei, language=a.sprache, vad_filter=not a.ohne_vad,
                                       beam_size=5, condition_on_previous_text=False)
    dauer = info.duration or 0
    t0 = time.time()
    with open(basis + ".srt", "w", encoding="utf-8") as srt, open(basis + ".txt", "w", encoding="utf-8") as txt:
        for i, s in enumerate(segmente, 1):
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

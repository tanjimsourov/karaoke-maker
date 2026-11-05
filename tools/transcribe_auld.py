from faster_whisper import WhisperModel
from pathlib import Path

root = Path(__file__).resolve().parents[1]
audio = root / "work/stems/htdemucs/auld_lang_syne/vocals.wav"
out = root / "work/lyrics/auld_whisper.txt"

model = WhisperModel("small.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    str(audio),
    beam_size=5,
    vad_filter=True,
    word_timestamps=True,
    initial_prompt="Auld Lang Syne. Should old acquaintance be forgot, and never brought to mind? For auld lang syne, my dear. We'll take a cup of kindness yet. We two have run about the hills. We two have paddled in the stream. And there's a hand, my trusty friend.",
)
lines = []
for seg in segments:
    lines.append(f"[{seg.start:07.2f} --> {seg.end:07.2f}] {seg.text.strip()}")
    if seg.words:
        lines.extend(f"  {w.start:07.2f}-{w.end:07.2f} {w.word}" for w in seg.words)
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))

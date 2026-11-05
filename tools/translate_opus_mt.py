"""Translate the performed Auld Lang Syne lyrics with a compact open model.

Model: Helsinki-NLP/opus-mt-en-da (MarianMT)
The result is saved both as a readable translation record and as a timed ASS
karaoke subtitle file for the three alternative-background samples.
"""

from pathlib import Path
import json
import re

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "Helsinki-NLP/opus-mt-en-da"

# Timings match the isolated-vocal performance. A four-second title lead-in is
# added when the ASS events are written.
CUES = [
    (0.0, 7.8, "Should old acquaintance be forgot and never brought to mind?"),
    (8.3, 15.9, "Should old acquaintance be forgot and days of auld lang syne?"),
    (16.3, 21.0, "For auld lang syne, my dear"),
    (21.0, 26.3, "For auld lang syne"),
    (26.3, 32.9, "We'll take a cup of kindness yet for auld lang syne"),
    (40.2, 46.0, "For auld lang syne, my dear"),
    (46.0, 51.4, "For auld lang syne"),
    (51.4, 57.0, "We'll take a cup of kindness yet"),
    (57.0, 63.6, "For auld lang syne"),
    (63.6, 71.8, "For auld lang syne, my dear"),
    (85.7, 93.7, "We two have paddled in the stream from morning sun till dine"),
    (93.7, 101.7, "But seas between us broad have roared since auld lang syne"),
    (102.0, 109.8, "For auld lang syne, my dear"),
    (109.8, 114.1, "We'll take a cup of kindness yet"),
    (114.1, 122.8, "For auld lang syne"),
    (123.0, 130.0, "And there's a hand, my trusty friend"),
    (130.0, 136.4, "And give me a hand of yours"),
    (136.4, 140.8, "We'll take a right good-will draught"),
    (142.8, 145.2, "For auld lang syne"),
]

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Karaoke,Arial,58,&H0000D7FF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,92,1
Style: Title,Arial,66,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,2,0,1,4,1,5,100,100,80,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def wrap(text: str, width: int = 43) -> str:
    if len(text) <= width:
        return text
    words = text.split()
    split_at = min(
        range(1, len(words)),
        key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))),
    )
    return " ".join(words[:split_at]) + r"\N" + " ".join(words[split_at:])


def karaoke(text: str, duration: float) -> str:
    tokens = re.split(r"(\s+|\\N)", wrap(text))
    words = [token for token in tokens if token and not token.isspace() and token != r"\N"]
    per_word = max(1, round(duration * 100 / max(1, len(words))))
    return "".join(
        token if token.isspace() or token == r"\N" else rf"{{\kf{per_word}}}{token}"
        for token in tokens
        if token
    )


def event(start: float, end: float, text: str, style: str = "Karaoke") -> str:
    rendered = text if style == "Title" else karaoke(text, end - start)
    return (
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{rendered}"
    )


def normalize_scots_for_model(text: str) -> str:
    """Express traditional Scots idioms in modern English before MT."""
    replacements = {
        "Should old acquaintance be forgot and never brought to mind?":
            "Should we forget old friends and never remember them?",
        "Should old acquaintance be forgot and days of auld lang syne?":
            "Should we forget old friends and the days of old times?",
        "We two have paddled in the stream from morning sun till dine":
            "We both rowed on the stream from morning until evening",
        "But seas between us broad have roared since auld lang syne":
            "But wide seas have roared between us since old times",
        "We'll take a right good-will draught":
            "We will share a hearty drink in goodwill",
        "Should old acquaintance be forgot": "Should old acquaintance be forgotten",
        "days of auld lang syne": "days of old times",
        "For auld lang syne": "For the sake of old times",
        "for auld lang syne": "for the sake of old times",
        "since auld lang syne": "since old times",
        "from morning sun till dine": "from morning sun until evening",
        "And there's a hand, my trusty friend": "And here is my hand, my trusted friend",
        "And give me a hand of yours": "And give me your hand",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def main() -> None:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
    source_lines = [source for _, _, source in CUES]
    model_lines = [normalize_scots_for_model(source) for source in source_lines]
    batch = tokenizer(model_lines, return_tensors="pt", padding=True, truncation=True)
    generated = model.generate(**batch, max_new_tokens=96, num_beams=5)
    translated = tokenizer.batch_decode(generated, skip_special_tokens=True)

    records = [
        {
            "start": start,
            "end": end,
            "english": source,
            "model_input": model_input,
            "danish": danish,
        }
        for (start, end, source), model_input, danish in zip(CUES, model_lines, translated)
    ]

    lyric_dir = ROOT / "work" / "lyrics" / "open_source"
    lyric_dir.mkdir(parents=True, exist_ok=True)
    (lyric_dir / "auld_lang_syne_opus_mt.json").write_text(
        json.dumps({"model": MODEL_ID, "lines": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (lyric_dir / "auld_lang_syne_opus_mt.txt").write_text(
        "\n".join(f"{i}. {item['danish']}" for i, item in enumerate(records, 1)) + "\n",
        encoding="utf-8",
    )

    subtitle_dir = ROOT / "work" / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    events = [event(0, 3.8, r"{\fad(300,300)}AULD LANG SYNE\N{\fs46}U.S. Navy Band", "Title")]
    events.extend(
        event(item["start"] + 4.0, item["end"] + 4.0, item["danish"])
        for item in records
    )
    (subtitle_dir / "auld_lang_syne_da_opus_mt.ass").write_text(
        HEADER + "\n".join(events) + "\n", encoding="utf-8"
    )

    print(json.dumps({"model": MODEL_ID, "translations": translated}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

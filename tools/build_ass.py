from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "work" / "subtitles"
OUT.mkdir(parents=True, exist_ok=True)

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
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def wrap_words(text: str, width: int = 43) -> str:
    words = text.split()
    if len(text) <= width:
        return text
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]) + r"\N" + " ".join(words[best:])

def karaoke(text: str, duration: float) -> str:
    wrapped = wrap_words(text)
    tokens = re.split(r"(\s+|\\N)", wrapped)
    words = [t for t in tokens if t and not t.isspace() and t != r"\N"]
    per = max(1, round(duration * 100 / max(1, len(words))))
    out = []
    for token in tokens:
        if token == r"\N":
            out.append(token)
        elif token.isspace():
            out.append(token)
        elif token:
            out.append(r"{\kf" + str(per) + "}" + token)
    return "".join(out)

def dialogue(start, end, text, style="Karaoke"):
    rendered = text if style == "Title" else karaoke(text, end - start)
    return f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{rendered}"

rehab_map = {
    "they tried": "De prøvede at tvinge mig til at gå i afvænning",
    "i said no": "Men jeg sagde: nej, nej, nej",
    "yes i've been black": "Ja, jeg har været nede, men når jeg kommer tilbage",
    "you'll know": "Vil du vide det, vide det, vide det",
    "i ain't got the time": "Jeg har ikke tid, og hvis min far synes, jeg har det fint",
    "just try to make": "Har han prøvet at tvinge mig til at gå i afvænning",
    "i won't go": "Men jeg vil ikke gå, gå, gå",
    "rather be at home": "Jeg vil hellere være hjemme hos Ray",
    "seventy days": "Jeg har ikke syvoghalvfjerds dage",
    "'cause there's nothing": "For der er intet",
    "there's nothing you can teach": "Intet, du kan lære mig",
    "mr hathaway": "Som jeg ikke kan lære af Mr. Hathaway",
    "a lot in class": "Jeg lærte ikke meget i klassen",
    "shot glass": "Men jeg ved, det ikke kommer i et shotglas",
    "why do": "Manden sagde: Hvorfor tror du, du er her?",
    "got no idea": "Jeg sagde: Jeg har ingen idé",
    "lose my baby": "Jeg vil, jeg vil miste min skat",
    "bottle near": "Så jeg har altid en flaske tæt ved",
    "you're depressed": "Han sagde: Jeg tror bare, du er trist",
    "and the rest": "Det er mig: Ja, skat, og alt det øvrige",
    "drink again": "Jeg vil aldrig drikke igen",
    "need a friend": "Jeg har bare brug for en ven",
    "spend ten weeks": "Jeg vil ikke bruge ti uger",
    "on the mend": "Få alle til at tro, jeg er på bedringens vej",
    "not just my pride": "Det handler ikke kun om stolthed",
    "tears have dried": "Det er bare, indtil tårerne er tørret væk",
}

def translate_rehab(text: str) -> str:
    t = text.lower().replace("\n", " ")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if "they tried" in t and "i said no" in t:
        return "De prøvede at tvinge mig til afvænning, men jeg sagde: nej, nej, nej"
    if "just try" in t and "i won't go" in t:
        return "De prøvede at tvinge mig til afvænning, men jeg vil ikke gå, gå, gå"
    for key, value in rehab_map.items():
        if key in t:
            return value
    return ""

vtt = (ROOT / "work" / "sources" / "rehab.en.vtt").read_text(encoding="utf-8")
rehab_lines = [dialogue(0, 3.45, r"{\fad(300,300)}REHAB\N{\fs46}Amy Winehouse", "Title")]
for block in re.split(r"\n\s*\n", vtt):
    m = re.search(r"(\d\d):(\d\d):(\d\d\.\d+)\s+-->\s+(\d\d):(\d\d):(\d\d\.\d+)[^\n]*\n(.+)", block, re.S)
    if not m:
        continue
    start = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    end = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6])
    raw = m[7].replace("â™ª", "").replace("♪", "")
    raw = re.sub(r"\([^)]*music[^)]*\)", "", raw, flags=re.I).strip()
    text = translate_rehab(raw)
    if text:
        rehab_lines.append(dialogue(start, end, text))
(OUT / "rehab_da.ass").write_text(HEADER + "\n".join(rehab_lines) + "\n", encoding="utf-8")

# Auld Lang Syne performance timings recovered from the isolated vocal track.
auld_cues = [
    (0.0, 7.8, "Skal gamle bekendtskaber glemmes og aldrig bringes i minde?"),
    (8.3, 15.9, "Skal gamle bekendtskaber glemmes og dage fra gamle tider?"),
    (16.3, 21.0, "For gamle tiders skyld, min kære"),
    (21.0, 26.3, "For gamle tiders skyld"),
    (26.3, 32.9, "Vi tager endnu en kop af venlighed for gamle tiders skyld"),
    (40.2, 46.0, "For gamle tiders skyld, min kære"),
    (46.0, 51.4, "For gamle tiders skyld"),
    (51.4, 57.0, "Vi tager endnu en kop af venlighed"),
    (57.0, 63.6, "For gamle tiders skyld"),
    (63.6, 71.8, "For gamle tiders skyld, min kære"),
    (85.7, 93.7, "Vi to har roet i strømmen fra morgenlys til skumringstime"),
    (93.7, 101.7, "Men brede have har brølt imellem os siden gamle tider"),
    (102.0, 109.8, "For gamle tiders skyld, min kære"),
    (109.8, 114.1, "Vi tager endnu en kop af venlighed"),
    (114.1, 122.8, "For gamle tiders skyld"),
    (123.0, 130.0, "Og her er hånden, min trofaste ven"),
    (130.0, 136.4, "Giv mig din hånd, jeg vil have den"),
    (136.4, 140.8, "Vi tager en skænk af hjertets lyst"),
    (142.8, 145.2, "For gamle tiders skyld"),
]
auld_lines = [dialogue(0, 3.8, r"{\fad(300,300)}AULD LANG SYNE\N{\fs46}U.S. Navy Band", "Title")]
for start, end, text in auld_cues:
    auld_lines.append(dialogue(start + 4.0, end + 4.0, text))
(OUT / "auld_lang_syne_da.ass").write_text(HEADER + "\n".join(auld_lines) + "\n", encoding="utf-8")

print(OUT / "rehab_da.ass")
print(OUT / "auld_lang_syne_da.ass")

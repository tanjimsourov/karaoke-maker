from pathlib import Path


root = Path(__file__).resolve().parents[1]
source = root / "work" / "subtitles" / "rehab_da.ass"
target = root / "work" / "subtitles" / "rehab_da_centered.ass"

text = source.read_text(encoding="utf-8")
text = text.replace(
    "Style: Karaoke,Arial,58,&H0000D7FF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,100,100,92,1",
    "Style: Karaoke,Arial,90,&H0000D7FF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,6,2,5,100,100,35,1",
)
text = text.replace(
    "Style: Title,Arial,66,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,2,0,1,4,1,5,100,100,80,1",
    "Style: Title,Arial,82,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,2,0,1,5,2,5,100,100,40,1",
)
target.write_text(text, encoding="utf-8")
print(target)

# Local-only code migration

The local pipeline and shared renderer were retained from the original karaoke workspace. Paid Karadeo/OpenL calls and browser/email automation were removed. The Friends adapter now executes and validates only its local result. Account configuration and Node browser dependencies were removed.

Preserved capabilities: separation, transcription, forced alignment, explicit review gates, OCR recovery, audio audit, branded rendering, validation and source-timeline preservation. Optional MarianMT translation is local but needs transformers and sentencepiece installed separately.

Model weights and source media are not included. No end-to-end or lyric-accuracy guarantee is made. Original code remains available in the sibling karaoke directory.

# FTP MP3 cloud automation

Goal: sequentially download MP3s, reuse the existing complete karaoke workflow
with a configured image background, atomically upload MP4s beside each source in
`karaoke/`, verify uploads, and clean completed local jobs. MP4 support remains.

1. Add regression tests for MP3 discovery, nested output exclusion, per-source
   destinations, exact source/output resume, and MP3 conversion command isolation.
2. Extend the existing FTP runner and use `karaoke.py run --automatic-export`.
   Keep original sources and shared model caches. Passwords use environment
   variables / Colab Secrets; never embed credentials in code or notebooks.
3. Add a Python cloud setup/run entry point and a reusable notebook, with explicit
   hardware/dependency checks, configurable backgrounds and bounded retries.
4. Run focused tests, inspect generated notebook/config, and publish code updates
   for normal GitHub pull. No GPU account rotation, paid resources or quotas bypass.

The exact Danish MP3 FTP folder and remote credentials must be supplied before
a real FTP batch. Automatic lyric inference is not human approval. Colab runtime
expiry can restart incomplete work; verified remote outputs are skipped.

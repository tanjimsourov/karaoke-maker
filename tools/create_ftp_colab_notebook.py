"""Generate the reusable cloud notebook without executing cloud conversion locally."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    cells=[]
    def markdown(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):cells.append({'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]})
    markdown('''# FTP MP3 to karaoke video
Run on a normally authorized Colab runtime. Do not rotate accounts to bypass limits.
All conversion runs in the cloud; no conversion is run on the desktop.

Default source: `/LH MP3 (actual situation in pre-defined)/Denmark Charts 2026`. Every source folder gets its own
`karaoke` subfolder. Original MP3s stay untouched.

Before Run all, add Colab Secrets `KARAOKE_FTP_USER` and `KARAOKE_FTP_PASSWORD`
using the key icon, and allow this notebook access. Credentials are never printed
or written to repository/config files. This server uses plain FTP port 2157.
The first run installs dependencies/models. Later songs reuse the model cache.
Free Colab can disconnect; rerun to skip checksum-verified remote uploads.
''')
    code('''from pathlib import Path
import subprocess, sys, os
PROJECT = Path('/content/karaoke-maker')
REPOSITORY = 'https://github.com/tanjimsourov/karaoke-maker.git'
COMPUTE = 'cuda'  # Use 'cpu' if a GPU is not available to this runtime.
if not PROJECT.exists():
    subprocess.run(['git','clone','--depth','1',REPOSITORY,str(PROJECT)],check=True)
else:
    origin=subprocess.check_output(['git','-C',str(PROJECT),'remote','get-url','origin'],text=True).strip()
    assert origin==REPOSITORY, 'Existing directory belongs to another repository'
    subprocess.run(['git','-C',str(PROJECT),'pull','--ff-only'],check=True)
subprocess.run([sys.executable,str(PROJECT/'tools/cloud_ftp_workspace.py'),'setup','--compute',COMPUTE],check=True)
''')
    code('''import json
CONFIG = PROJECT/'config/ftp-mp3-danish.json'
settings=json.loads(CONFIG.read_text())
# Change these settings when selecting another FTP folder/background.
settings.update(input_folder='/LH MP3 (actual situation in pre-defined)/Denmark Charts 2026', background_folder='assets/audio-bg',
                language='da', output_layout='beside-source', limit=0)
# limit=3 processes three not-yet-completed songs; limit=0 processes the whole folder.
CONFIG = PROJECT/'tmp/my-ftp-mp3-settings.json'
CONFIG.write_text(json.dumps(settings,indent=2))
print('Source:',settings['input_folder'])
print('Background pool:',settings['background_folder'])
print('Output: karaoke subfolder beside each MP3')
''')
    code('''from google.colab import userdata
for name in ('KARAOKE_FTP_USER','KARAOKE_FTP_PASSWORD'):
    os.environ[name]=userdata.get(name)
result=subprocess.run([sys.executable,str(PROJECT/'tools/cloud_ftp_workspace.py'),'run',
                       '--config',str(CONFIG),'--compute',COMPUTE])
if result.returncode:
    raise RuntimeError('Batch ended with one or more unsuccessful songs; inspect console output')
print('Batch completed. Videos are on FTP beside the source MP3s in karaoke/.')
''')
    notebook={'cells':cells,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3'},
                                      'language_info':{'name':'python'},'colab':{'name':'FTP MP3 Karaoke.ipynb'}},
              'nbformat':4,'nbformat_minor':5}
    destination=ROOT/'notebooks/FTP_MP3_Karaoke.ipynb'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(notebook,indent=2),encoding='utf-8')
    print(destination)


if __name__=='__main__':main()

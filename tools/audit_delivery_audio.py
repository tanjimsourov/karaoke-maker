from pathlib import Path
import subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
FF=ROOT/'tools/ffmpeg/ffmpeg.exe'
songs=[('AEr_lig_Freestyle','Ærlig Freestyle.mp3'),('Bliv_her_lidt_endnu','Bliv her lidt endnu.mp3'),('Blodigt','Blodigt.mp3'),('Barry_Cant_Swim_Kimbara',"Barry Can't Swim - 'Kimbara' (Official Visualiser).mp3"),('BUNT_TRIPPIN','BUNT. - TRIPPIN.mp3')]
def levels(path):
    r=subprocess.run([str(FF),'-v','error','-i',str(path),'-ar','8000','-ac','1','-f','f32le','-'],capture_output=True,check=True)
    a=np.frombuffer(r.stdout,dtype=np.float32)
    n=len(a)//160
    return 20*np.log10(np.maximum(1e-9,np.sqrt(np.mean(a[:n*160].reshape(n,160)**2,axis=1))))
def gaps(a):
    low=a<-48
    edges=np.diff(np.r_[False,low,False].astype(int))
    return [(round(s*.02,2),round(e*.02,2)) for s,e in zip(np.where(edges==1)[0],np.where(edges==-1)[0]) if (e-s)*.02>=.4]
for slug,name in songs:
    src=levels(ROOT/'Bowlnfun Jakob For Visuals'/name)
    ins=levels(ROOT/'work/bowlnfun'/slug/'instrumental.mp3')
    videos=list((ROOT/'out').glob(slug+'*.mp4'))
    final=levels(videos[0])
    print(slug,flush=True)
    print('  source quiet intervals',gaps(src))
    print('  instrumental quiet intervals',gaps(ins))
    print('  delivery quiet intervals',gaps(final))
    for label,a in [('source',src),('instrumental',ins),('video',final)]:
        print(' ',label,'30-42s dB', [round(float(np.mean(a[t*50:(t+1)*50])),1) for t in range(30,43)])

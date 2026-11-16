"""Screen lyric colour masks. Profile names describe base -> highlighted colour."""
import numpy as np

PROFILES={'white-blue':2,'blue-yellow':0,'white-magenta':3,'magenta-white':4}


def colours(frame,k):
    b,g,r=[frame[:,:,index].astype(np.float32) for index in range(3)]
    blue=(b>r+35)&(b>g+20)&(b>65)
    white=(np.minimum(np.minimum(r,g),b)>160)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<45)
    pink=(r>120)&(b>75)&(g<r*.7)
    if k==0:return (r>150)&(g>150)&(b<100)&(abs(r-g)<65),blue|pink
    if k==3:return pink,white
    if k==4:return white,pink
    if k in (1,2):return blue,white
    raise ValueError('Unsupported colour profile index')

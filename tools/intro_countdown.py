"""Reference-style white countdown arc, independent of vocal start time."""
import math
import os
import re
from pathlib import Path


def first_visible_frame(source,destination,with_time=False):
    """Select an intro still without trimming/re-timing the actual music video."""
    import av
    import numpy as np
    first=None
    chosen=None
    chosen_time=0.0
    with av.open(str(source)) as container:
        for frame in container.decode(video=0):
            if first is None:first=frame.to_image()
            pixels=frame.to_ndarray(format='gray')
            if np.mean(pixels>20)>.08:
                chosen=frame.to_image();chosen_time=float(frame.time or 0);break
            if frame.time is not None and frame.time>=3:break
    if first is None:raise ValueError('Background video has no frames')
    (chosen if chosen is not None else first).save(destination)
    return (Path(destination),chosen_time) if with_time else Path(destination)


def events(seconds, fps, width, height, ass_time):
    if not math.isfinite(seconds) or seconds <= 0:
        return []
    scale=min(width,height)/1080
    cx,cy=width/2,330*height/1080
    result=[]
    for number in range(math.ceil(seconds),0,-1):
        start=max(0,seconds-number)
        stop=min(seconds,seconds-number+1)
        result.append(f'Dialogue: 4,{ass_time(start)},{ass_time(stop)},PageBase,,0,0,0,,{{\\pos({round(cx)},{round(690*height/1080)})\\fs{round(110*scale)}\\1c&HFFFFFF&\\bord{round(5*scale)}}}{number}')
    return result


def settings(style=None,colour=None):
    style=style if style is not None else os.environ.get('KARAOKE_COUNTDOWN_STYLE','arc')
    colour=colour if colour is not None else os.environ.get('KARAOKE_COUNTDOWN_COLOUR','#FFFFFF')
    if style not in ('arc','circle'):raise ValueError('countdown_style must be arc or circle')
    if not isinstance(colour,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',colour):
        raise ValueError('countdown_colour must be #RRGGBB')
    return {'countdown_style':style,'countdown_colour':colour.upper()}


def reference_logo_filter(seconds,scale=1,style=None,colour=None):
    """Complete logo plus a geometric clockwise closing ring, without a track.

    Historical function name retained for callers. The ring is independent of
    artwork shape/colour; the central logo pixels are never erased or whitened.
    """
    if not math.isfinite(seconds) or seconds<=0 or not math.isfinite(scale) or scale<=0:
        raise ValueError('Countdown duration and scale must be positive and finite')
    options=settings(style,colour);style=options['countdown_style'];colour=options['countdown_colour']
    size=round(420*scale);canvas=round(500*scale);pad=(canvas-size)//2
    angle='mod(atan2(Y-H/2,X-W/2)+PI/2+2*PI,2*PI)'
    ring=f'between(hypot(X-W/2,Y-H/2),{231*scale:g},{239*scale:g})'
    ring+=f'*gte({angle},2*PI*T/{seconds:.3f})' if style=='arc' else f'*lt(T,{seconds:.3f})'
    alpha=f'max(alpha(X,Y),255*{ring})'
    channels={c:f'if({ring},{int(colour[1+2*i:3+2*i],16)},{c}(X,Y))' for i,c in enumerate('rgb')}
    return (f'scale={size}:{size},format=rgba,pad={canvas}:{canvas}:{pad}:{pad}:color=black@0,'
            f"geq=r='{channels['r']}':g='{channels['g']}':b='{channels['b']}':a='{alpha}'")


def logo_without_outer_ring(source, destination):
    """Remove only isolated outer components from the bundled transparent logo.

    Original corner artwork is always retained. A custom opaque logo is returned
    unchanged; this function never crops its central artwork by radius.
    """
    import numpy as np
    from PIL import Image
    from scipy.ndimage import label,find_objects
    rgba=np.array(Image.open(source).convert('RGBA'))
    h,w=rgba.shape[:2]
    labels,_=label(rgba[:,:,3]>0)
    for index,bounds in enumerate(find_objects(labels),1):
        if bounds is None:continue
        y,x=bounds
        # Components reaching the edge on an opaque/custom canvas are not rings.
        if x.start==0 or y.start==0 or x.stop==w or y.stop==h:continue
        if x.start<w*.1 or x.stop>w*.9 or y.start<h*.1 or y.stop>h*.9:
            mask=labels==index
            pixels=rgba[mask,:3]
            if len(pixels) and (pixels.min(axis=1)>200).mean()>.9:
                rgba[mask,3]=0
    Image.fromarray(rgba).save(destination)
    return Path(destination)

"""Plan source-credit cleanup for the final encode, without an intermediate MP4.

Final output OCR remains mandatory. A mask plan is not a clean-output certificate.
"""
from pathlib import Path
import math
from zoom_local_pipeline import digest, read, save


def masks_from_report(report):
    if not report.get('complete'):
        raise ValueError('Incomplete source branding scan')
    merged = []
    for hit in sorted(report['hits'], key=lambda h: h['time']):
        if 'credit_box' not in hit:
            raise ValueError('Unlocated source mark requires manual correction')
        sw, sh = hit['scan_size']; fw, fh = hit['frame_size']
        x1, y1, x2, y2 = hit['credit_box']
        x = max(1, int(x1*fw/sw)-12); y = max(1, int(y1*fh/sh)-12)
        w = min(fw-1, math.ceil(x2*fw/sw)+12)-x
        h = min(fh-1, math.ceil(y2*fh/sh)+12)-y
        start, end = max(0, hit['time']-1.5), hit['time']+1.5
        match = next((i for i,m in enumerate(merged) if start <= m[5]+.1
                      and abs(x-m[0]) < 80 and abs(y-m[1]) < 150), None)
        if match is None:
            merged.append([x,y,w,h,start,end])
        else:
            a,b,c,d,s,e = merged[match]; left=min(x,a); top=min(y,b)
            merged[match] = [left,top,max(x+w,a+c)-left,max(y+h,b+d)-top,min(s,start),max(e,end)]
    return merged


def prepare(source, folder):
    from branding_guard import resolved_background, scan, BrandingDetected
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    # Preserve previously completed cleanup instead of repeating it.
    cached = resolved_background(source, folder)
    if cached != str(source):
        return cached, None
    report = folder/'source-scan.json'
    try:
        scan(source, report)
    except BrandingDetected:
        pass
    plan = {'source_sha256': digest(source), 'masks': masks_from_report(read(report)),
            'status': 'planned_only_requires_output_scan'}
    path = folder/'inline-plan.json'; save(path, plan)
    return str(source), path


def filters(source, plan, at_time=None):
    data = read(plan)
    if data['source_sha256'] != digest(source):
        raise ValueError('Branding plan source changed')
    result = []
    for mask in data['masks']:
        if len(mask) != 6 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in mask):
            raise ValueError('Invalid branding mask')
        x,y,w,h,start,end = mask
        if min(x,y,w,h) < 1 or start < 0 or end <= start:
            raise ValueError('Invalid branding bounds')
        if at_time is not None and not start <= at_time <= end:continue
        enable=f":enable='between(t,{start:.3f},{end:.3f})'" if at_time is None else ''
        result.append(f"delogo=x={int(x)}:y={int(y)}:w={int(w)}:h={int(h)}{enable}")
    return ','.join(result)

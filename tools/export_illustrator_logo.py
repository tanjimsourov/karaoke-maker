"""Rasterize PDF-compatible Illustrator artwork directly, retaining alpha."""
import argparse,json,shutil
from pathlib import Path
import pymupdf
from PIL import Image
from project_runtime import ROOT

def export(source,size=2048):
 source=Path(source)
 with pymupdf.open(source) as doc:
  if len(doc)!=1:raise ValueError('Expected a one-page logo')
  page=doc[0];scale=size/max(page.rect.width,page.rect.height)
  result={}
  for alpha,label in [(False,'White Background'),(True,'Transparent')]:
   path=source.with_name(source.stem+' - '+label+'.png')
   if path.exists():raise FileExistsError(path)
   page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=alpha).save(path)
   result[label]=str(path)
  rgba=Image.open(result['Transparent']).convert('RGBA')
  assert rgba.getchannel('A').getextrema()==(0,255)
  asset=ROOT/'assets/logo-karaoke-cmyk-transparent.png'
  if asset.exists():raise FileExistsError(asset)
  shutil.copyfile(result['Transparent'],asset)
  result.update(asset=str(asset),dimensions=rgba.size,source=str(source),renderer=pymupdf.VersionBind)
 report=ROOT/'reports/illustrator-logo';report.mkdir(exist_ok=True)
 (report/'export.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--size',type=int,default=2048);a=p.parse_args();export(a.source,a.size)

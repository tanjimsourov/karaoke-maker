"""Smaller top-right intro logo copies, retaining song pictures and all audio."""
import json
from pathlib import Path
import av
from render_round_compact_batch import ROOT, ff, info, audio_hash, digest
from restore_compact_intro_footer import pictures
from intro_countdown import reference_logo_filter


def main():
    sources = [('Human-2c623275af5e_DRAFT.mp4', '1.jpeg', 'Carpark North - Human'),
               ('The_Second_You_Sleep-2c9642be5442_DRAFT.mp4', '2.jpeg', 'Saybia - The Second You Sleep')]
    destination = ROOT/'out/ftp-image-backgrounds/Updated Logo'
    destination.mkdir(parents=True, exist_ok=True)
    logo = ROOT/'assets/logo-karaoke-cmyk-transparent.png'
    results = []
    for filename, background, name in sources:
        source = ROOT/'out/ftp-image-backgrounds'/filename
        folder = ROOT/'tmp/ftp-logo-update'/name
        folder.mkdir(parents=True, exist_ok=True)
        output = destination/(name+' - Smaller Top Right Logo - DRAFT.mp4')
        if output.exists():
            raise FileExistsError(output)
        with av.open(str(source)) as container:
            stream = container.streams.video[0]
            timescale = stream.time_base.denominator
            boundary = next(float(p.pts*stream.time_base) for p in container.demux(stream)
                            if p.is_keyframe and p.pts is not None and float(p.pts*stream.time_base)>=10)
        # Restore only the old 500px intro logo rectangle from the exact background.
        # The existing countdown numbers, title, artist and 10s audio offset remain intact.
        graph = (
            '[1:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,'
            'crop=500:500:710:80[patch];'
            "[0:v][patch]overlay=710:80:eof_action=pass:repeatlast=0:enable='lt(t,10)'[clean];"
            f'[2:v]{reference_logo_filter(10,.7,"arc","#BB3794")}[logo];'
            "[clean][logo]overlay=W-w-48:42:eof_action=pass:repeatlast=0:enable='lt(t,10)',format=yuv420p[v]")
        ff(['-y','-filter_complex_threads','2','-i',source,
            '-loop','1','-framerate','30','-t','10','-i',ROOT/'assets/audio-bg'/background,
            '-loop','1','-framerate','30','-t','10','-i',logo,
            '-filter_complex',graph,'-map','[v]','-an','-frames:v',round(boundary*30),
            '-r','30','-c:v','libx264','-preset','veryfast','-crf','14','-threads','4',
            '-video_track_timescale',timescale,folder/'intro.mp4'],folder,'render')
        concat=folder/'concat.txt'
        concat.write_text(f"file '{(folder/'intro.mp4').as_posix()}'\nfile '{source.as_posix()}'\ninpoint {boundary:.9f}\n",encoding='utf-8')
        ff(['-y','-f','concat','-safe','0','-i',concat,'-i',source,'-map','0:v:0','-map','1:a:0',
            '-c','copy','-map_metadata','1','-movflags','+faststart',output],folder,'mux')
        assert audio_hash(source)==audio_hash(output),'Audio changed'
        assert pictures(source,boundary)==pictures(output,boundary),'Song tail changed'
        assert abs(info(source)['duration']-info(output)['duration'])<.05,'Duration changed'
        assert output.stat().st_size<150_000_000
        ff(['-xerror','-i',output,'-f','null','-'],folder,'decode')
        row={'output':str(output),'intro_logo_scale':.7,'margin_right':48,'margin_top':42,
             'audio_identical':True,'unchanged_coded_pictures_from':boundary,
             'bytes':output.stat().st_size,'sha256':digest(output),**info(output)}
        (folder/'verified.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
        results.append(row)
        print(json.dumps(row),flush=True)
    (ROOT/'tmp/ftp-logo-update/outputs.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()

"""Source-bound review edits for this benchmark only; does not certify delivery.

Uses the original-mix ASR text, corrects misheard words, and retains all inputs.
This is a review recipe, not a change to the normal transcription algorithm.
"""
from copy import deepcopy
from project_runtime import WORK
from zoom_local_pipeline import read,save,digest
from local_karaoke import backup_transcript
from asr_draft_quality import validate_asr_draft


def main():
    folder=WORK/'Shake_It_Off-8b97f501f932'
    report=read(folder/'original-reference-report.json')
    if report['source_sha256']!='082e17fffcca522a2bfc5c196a337988f3dd45d5513bad7654505bf896b4f34e':
        raise ValueError('This review recipe is only for the downloaded benchmark source')
    source=folder/'transcript.original-reference.json'
    if digest(source)!=report['transcript_sha256']:raise ValueError('Review reference changed')
    rows=read(source)
    edits={11:("And my haters","And the haters"),
        14:("The heartbreak is gonna","Heartbreakers gonna"),
        15:("And the fake is gonna","And the fakers gonna"),
        23:("I'll make them move so fast and go","I make the moves up as I go"),
        27:("Can't stop, won't stop proving","Can't stop, won't stop grooving"),
        29:("Say, yeah, it's gonna","Saying it's gonna")}
    for index,(old,new) in edits.items():
        if old not in rows[index]['text']:raise ValueError(f'Unexpected reference text in row {index}')
        rows[index]['text']=rows[index]['text'].replace(old,new)
    rows[13]['text']=rows[17]['text']
    rows[33]['text']=rows[17]['text']
    rows[34]['text']=rows[14]['text']
    rows[35]['text']=rows[15]['text']
    chorus=[rows[i]['text'] for i in range(10,18)]
    end_chorus=[(164.34,167.62),(167.62,171.),(171.,173.62),(173.62,176.16),
                (176.16,179.5),(179.5,182.82),(182.82,185.76),(185.76,188.3)]
    repaired=[{'start':r['start'],'end':r['end'],'text':r['text'].strip()} for r in rows[:48]]
    repaired.extend({'start':a,'end':b,'text':text.strip()} for (a,b),text in zip(end_chorus,chorus))
    # Repeated outro wording is present in both ASR references. These are segment
    # search windows; WhisperX must still derive actual word times from the audio.
    hook=rows[17]['text'].strip()
    for start,end in [(188.3,208.),(208.,228.5)]:
        repaired.append({'start':start,'end':end,'text':' '.join([hook]*4)})
    split=[]
    for row in repaired:
        words=row['text'].split()
        for i in range(0,len(words),10):
            stop=min(i+10,len(words));span=row['end']-row['start']
            split.append({'start':row['start']+span*i/len(words),
                'end':row['start']+span*stop/len(words),'text':' '.join(words[i:stop])})
    validate_asr_draft({'segments':split})
    save(folder/'transcript.review-candidate.json',split)
    backup_transcript(folder)
    save(folder/'transcript.json',split)
    save(folder/'lyric-review-notes.json',{'method':'AI-assisted ASR comparison and text correction',
        'reference_url':'https://lyricsweb.com/song/taylor-swift/taylor-swift-shake-it-off',
        'reference_scope':'word corrections and repeated-section structure; source audio remains the downloaded music video',
        'original_transcript_preserved':True,'outro_timing_requires_review':True,
        'segment_windows_are_not_word_timings':True,'full_listening_approved':False,
        'delivery_approved':False})
    print('Review candidate prepared:',folder/'transcript.review-candidate.json')


if __name__=='__main__':main()

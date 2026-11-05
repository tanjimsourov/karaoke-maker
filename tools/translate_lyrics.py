"""Lyric translation engines. Every engine returns exactly one line per lyric line,
so each translation keeps its original line's timing.

llm  - a large language model over the OpenAI-compatible chat API, translating
       the whole song in context (like OpenL). Default endpoint is a local
       Ollama server: free and offline. LLM_URL / LLM_MODEL / LLM_API_KEY
       select another local or paid provider.
opus - Helsinki-NLP/opus-mt-<src>-<tgt> (MarianMT), line by line, pivoting
       through English when no direct model exists. Fast, literal, no server.
"""
from __future__ import annotations
import json
import os
import re
import urllib.error
import urllib.request

MODEL = 'Helsinki-NLP/opus-mt-{}-{}'
MODES = ('below', 'only')
ENGINES = ('llm', 'opus')
STYLES = ('natural', 'singable', 'literal')
LLM_URL = 'http://localhost:11434/v1/chat/completions'
LLM_MODEL = 'qwen2.5:7b-instruct'
CHUNK = 40
LANGUAGE_NAMES = {'da': 'Danish', 'en': 'English', 'es': 'Spanish', 'sv': 'Swedish', 'no': 'Norwegian',
                  'nb': 'Norwegian', 'de': 'German', 'fr': 'French', 'it': 'Italian', 'nl': 'Dutch',
                  'pt': 'Portuguese', 'pl': 'Polish', 'fi': 'Finnish', 'bn': 'Bengali', 'ar': 'Arabic'}
STYLE_RULES = {
    'natural': 'Write fluent, idiomatic lyrics a native speaker would say; keep the meaning, mood and slang level.',
    'singable': 'Keep each line close to the original syllable count and rhythm so it can be sung to the same melody; keep rhymes where possible.',
    'literal': 'Stay close to the literal meaning, still in correct grammar.',
}


def clean(text):
    """No ASS markup may reach the subtitle file."""
    return ' '.join(re.sub(r'[{}\\]', '', text).split())


def lines_from_aligned(segments):
    """Timed lyric lines from aligned.json, using the first and last word times."""
    lines = []
    for segment in segments:
        words = [w for w in segment.get('words', []) if 'start' in w and 'end' in w]
        text = clean(segment.get('text', ''))
        if not words or not text:
            continue
        lines.append({'start': round(words[0]['start'], 3), 'end': round(words[-1]['end'], 3), 'text': text})
    if not lines:
        raise ValueError('aligned.json has no timed lines; run align first')
    return lines


def model_chain(source, target, exists):
    """Model ids to apply in order. `exists(model_id)` reports availability."""
    if source == target:
        raise ValueError('Song is already in the target language')
    direct = MODEL.format(source, target)
    if exists(direct):
        return [direct]
    chain = [MODEL.format(source, 'en'), MODEL.format('en', target)]
    chain = [m for m, needed in zip(chain, (source != 'en', target != 'en')) if needed]
    missing = [m for m in chain if not exists(m)]
    if missing:
        raise ValueError(f'No Opus-MT model for {source}->{target} (missing {", ".join(missing)})')
    return chain


def hub_model_exists(model_id):
    from huggingface_hub import HfApi, try_to_load_from_cache
    from huggingface_hub.utils import RepositoryNotFoundError
    if isinstance(try_to_load_from_cache(model_id, 'config.json'), str):
        return True  # already downloaded: works offline
    try:
        HfApi().model_info(model_id)
        return True
    except RepositoryNotFoundError:
        return False


def language_name(code):
    return LANGUAGE_NAMES.get(code, code)


def system_rules(source, target, style, glossary, brief='', instructions=''):
    rules = [
        f'You are a professional song translator from {language_name(source)} to {language_name(target)} '
        'writing karaoke subtitles.',
        STYLE_RULES[style],
        'Repeated lines get the same translation; pronouns, tense and tone stay consistent across the song.',
        'Keep personal names, brand names and untranslatable vocal sounds (oh, yeah, la la) unchanged.',
        'Subtitles must be short enough to read while singing: no longer than the original needs.',
        'Handle each line separately: never merge, split, drop, reorder or explain lines.',
    ]
    if glossary:
        rules.append('Always use these fixed translations: ' + '; '.join(f'"{k}" -> "{v}"' for k, v in glossary.items()))
    if brief:
        rules.append('Song brief (use it for meaning and tone): ' + brief)
    if instructions:
        rules.append('Extra instructions from the editor: ' + instructions)
    return ' '.join(rules)


def numbered(lines):
    return '\n'.join(f'{i}. {line}' for i, line in enumerate(lines, 1))


def ask_lines(send, system, prompt, count, attempts=3):
    """One chat call that must return exactly `count` strings; retried with feedback."""
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': prompt + f'\n\nReply with only a JSON array of exactly {count} strings.'}]
    for attempt in range(attempts):
        try:
            return parse_llm_reply(send(messages), count)
        except (ValueError, json.JSONDecodeError) as exc:
            if attempt == attempts - 1 or 'not reachable' in str(exc):
                raise
            messages = messages + [{'role': 'user', 'content':
                f'Invalid answer ({exc}). Reply with only the JSON array of exactly {count} strings.'}]


def parse_llm_reply(reply, count):
    """The model's JSON array, tolerating code fences or text around it."""
    match = re.search(r'\[.*\]', reply, re.S)
    if not match:
        raise ValueError('LLM reply has no JSON array')
    values = json.loads(match.group(0))
    if not isinstance(values, list) or len(values) != count or not all(isinstance(v, str) for v in values):
        raise ValueError(f'LLM returned {len(values) if isinstance(values, list) else "invalid"} lines, expected {count}')
    return [re.sub(r'^\s*\d+[.)]\s*', '', v) for v in values]


def chat(messages, url=None, model=None, api_key=None, timeout=600):
    url = url or os.environ.get('LLM_URL', LLM_URL)
    body = {'model': model or os.environ.get('LLM_MODEL', LLM_MODEL), 'messages': messages,
            'temperature': 0.2, 'stream': False}
    headers = {'Content-Type': 'application/json'}
    key = api_key or os.environ.get('LLM_API_KEY')
    if key:
        headers['Authorization'] = f'Bearer {key}'
    request = urllib.request.Request(url, json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())['choices'][0]['message']['content']
    except urllib.error.URLError as exc:
        raise ValueError(f'LLM server not reachable at {url} ({exc}). Start Ollama and pull {body["model"]}, '
                         'or use --engine opus') from exc


def song_brief(texts, source, send):
    """Pass 1: understand the song before translating any line."""
    messages = [
        {'role': 'system', 'content': 'You analyse song lyrics for a translator. Answer in English, under 120 words.'},
        {'role': 'user', 'content': f'{language_name(source)} lyrics:\n' + '\n'.join(texts) + '\n\n'
         'Describe: the story and theme; who sings to whom (gender/number if clear); mood and register '
         '(slang, formal, playful); idioms, wordplay or cultural references and what they mean; names to keep.'}]
    return ' '.join(send(messages).split())


def in_chunks(count):
    return [(start, min(start + CHUNK, count)) for start in range(0, count, CHUNK)]


def draft_pass(texts, system, send, fixed):
    """Pass 2: translate in chunks, each seeing the previous translated lines as context."""
    out = []
    for start, end in in_chunks(len(texts)):
        prompt = ''
        context = list(zip(texts[max(0, start - 12):start], out[max(0, start - 12):start]))
        if context:
            prompt += 'Previous lines, already translated (context only):\n' + \
                      '\n'.join(f'{a} => {b}' for a, b in context) + '\n\n'
        locked = {i - start + 1: fixed[i] for i in range(start, end) if i in fixed}
        if locked:
            prompt += 'Use exactly these approved translations for the given line numbers: ' + \
                      '; '.join(f'{n}: "{t}"' for n, t in locked.items()) + '\n\n'
        prompt += 'Translate these lines:\n' + numbered(texts[start:end])
        try:
            out += ask_lines(send, system, prompt, end - start)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f'Lines {start + 1}-{end}: {exc}') from exc
    return out


def refine_pass(texts, drafts, system, send):
    """Pass 3: an editor compares every line with the original and fixes it."""
    out = []
    for start, end in in_chunks(len(texts)):
        pairs = '\n'.join(f'{i}. {a}\n   draft: {b}' for i, (a, b) in
                          enumerate(zip(texts[start:end], drafts[start:end]), 1))
        prompt = ('Edit this draft translation. For each line fix mistranslations, missed idioms or slang, '
                  'unnatural word order, inconsistent repeated lines and lines too long to read while singing. '
                  'Keep a line unchanged when it is already good.\n\n' + pairs)
        try:
            out += ask_lines(send, system, prompt, end - start)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f'Refining lines {start + 1}-{end}: {exc}') from exc
    return out


def review_pass(texts, final, source, target, send):
    """Pass 4: back-translate and name lines whose meaning drifted ('' when fine)."""
    notes = []
    for start, end in in_chunks(len(texts)):
        back = ask_lines(send, f'Translate {language_name(target)} song lines to {language_name(source)} literally.',
                         numbered(final[start:end]), end - start)
        pairs = '\n'.join(f'{i}. original: {a}\n   back-translated: {b}' for i, (a, b) in
                          enumerate(zip(texts[start:end], back), 1))
        notes += ask_lines(send, 'You check song translations for meaning errors.',
                           'For each line compare the original with the back-translation of our translation. '
                           'Write "" when the meaning matches, otherwise a short note (under 12 words) saying '
                           'what changed or is lost.\n\n' + pairs, end - start)
    return notes


def length_flags(texts, final):
    """Lines too long to read in time, measured against the original."""
    return [len(b) > max(28, 1.5 * len(a)) for a, b in zip(texts, final)]


def shorten_pass(texts, final, system, send):
    """Pass 5: shorten only the lines that are too long for a subtitle."""
    long_lines = [i for i, flag in enumerate(length_flags(texts, final)) if flag]
    if not long_lines:
        return final
    prompt = ('These translated lines are too long to read while singing. Shorten each one, keeping the '
              'meaning:\n' + '\n'.join(f'{n}. original: {texts[i]}\n   long: {final[i]}'
                                       for n, i in enumerate(long_lines, 1)))
    shorter = ask_lines(send, system, prompt, len(long_lines))
    final = list(final)
    for i, text in zip(long_lines, shorter):
        if text.strip() and len(text) < len(final[i]):
            final[i] = text
    return final


def translate_llm(texts, source, target, style='natural', glossary=None, send=chat,
                  quality='best', instructions='', memory=None, progress=print):
    """Whole-song translation. quality 'best' runs brief, draft, refine, shorten and review
    passes; 'fast' only drafts. `memory` maps source lines to approved translations, which
    are kept verbatim. Returns (translations, per-line review notes, brief)."""
    if source == target:
        raise ValueError('Song is already in the target language')
    if style not in STYLES:
        raise ValueError(f'style must be one of {STYLES}')
    if quality not in ('best', 'fast'):
        raise ValueError("quality must be 'best' or 'fast'")
    fixed = {i: memory[t] for i, t in enumerate(texts) if memory and t in memory}
    brief = ''
    if quality == 'best':
        progress('Pass 1/5: reading the whole song')
        brief = song_brief(texts, source, send)
    system = system_rules(source, target, style, glossary or {}, brief, instructions)
    progress('Pass 2/5: draft translation' if quality == 'best' else 'Translating')
    final = draft_pass(texts, system, send, fixed)
    notes = [''] * len(texts)
    if quality == 'best':
        progress('Pass 3/5: editing against the original')
        final = refine_pass(texts, final, system, send)
        progress('Pass 4/5: shortening long subtitle lines')
        final = shorten_pass(texts, final, system, send)
    for i, text in fixed.items():
        final[i] = text  # approved translations always win
    final = [clean(t) for t in final]
    if quality == 'best':
        progress('Pass 5/5: back-translation meaning check')
        notes = [clean(n).strip('"') for n in review_pass(texts, final, source, target, send)]
        for i in fixed:
            notes[i] = ''
    for i, too_long in enumerate(length_flags(texts, final)):
        if too_long:
            notes[i] = (notes[i] + '; ' if notes[i] else '') + 'long for a subtitle'
    return final, notes, brief


def memory_path(root):
    return root / 'work' / 'translation_memory.json'


def load_memory(root, source, target):
    path = memory_path(root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8')).get(f'{source}-{target}', {})


def add_to_memory(root, source, target, pairs):
    """Accepted translations are reused verbatim in later songs (translation memory)."""
    path = memory_path(root)
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data.setdefault(f'{source}-{target}', {}).update({a: b for a, b in pairs if a and b})
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def translate(texts, chain, device='cpu', batch_size=16):
    from transformers import MarianMTModel, MarianTokenizer
    for model_id in chain:
        tokenizer = MarianTokenizer.from_pretrained(model_id)
        model = MarianMTModel.from_pretrained(model_id).to(device)
        out = []
        for i in range(0, len(texts), batch_size):
            batch = tokenizer(texts[i:i+batch_size], return_tensors='pt', padding=True, truncation=True).to(device)
            generated = model.generate(**batch, max_new_tokens=128, num_beams=5)
            out += tokenizer.batch_decode(generated, skip_special_tokens=True)
        texts = out
    return [clean(t) for t in texts]

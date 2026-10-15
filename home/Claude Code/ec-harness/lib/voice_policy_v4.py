"""V4-only request policy. Pure validation; no network, credentials or generation."""
import math
import re
MODEL = 'eleven_v4'
POLICY_VERSION = 'eleven-v4-only-20261004-r1'

def require_model(model):
    if model != MODEL:
        raise ValueError('Only eleven_v4 is authorized; legacy models and fallback are disabled')
    return model

def require_voice(voice):
    if not isinstance(voice, str) or not re.fullmatch(r'[A-Za-z0-9]{20}', voice):
        raise ValueError('An explicit existing ElevenLabs voice ID is required; no voice substitution')
    return voice

def require_settings(settings):
    if not isinstance(settings, dict) or set(settings) != {'stability', 'similarity_boost'}:
        raise ValueError('V4 accepts only stability and similarity_boost here; style/speed/boost are unsupported')
    for value in settings.values():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('V4 stability/similarity must be finite numbers in [0, 1]')
    return dict(settings)

def payload(text, model, voice, stability=.5, similarity=.8, dictionaries=None):
    require_model(model); require_voice(voice)
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise ValueError('V4 requires nonempty text within 10000 characters')
    if re.search(r'<\s*/?\s*(?:speak|break|phoneme|prosody|say-as)\b', text, re.I):
        raise ValueError('SSML is not supported by V4; supply explicit native text')
    body = {'text': text, 'model_id': MODEL, 'language_code': 'ja',
            'voice_settings': require_settings({'stability': stability, 'similarity_boost': similarity})}
    if dictionaries is not None:
        if not isinstance(dictionaries, list) or len(dictionaries) > 3:
            raise ValueError('At most three explicit pronunciation dictionaries are supported')
        for locator in dictionaries:
            if not isinstance(locator, dict) or set(locator) != {'pronunciation_dictionary_id', 'version_id'} or any(not isinstance(v, str) or not v.strip() for v in locator.values()):
                raise ValueError('Exact dictionary ID and version are required; no dictionary substitution')
        body['pronunciation_dictionary_locators'] = dictionaries
    return body

def cache_fingerprint(context):
    import hashlib, json
    return hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def cache_proof(context, audio_path):
    from pathlib import Path
    import hashlib
    return {'policy': POLICY_VERSION, 'context_sha256': cache_fingerprint(context),
            'audio_sha256': hashlib.sha256(Path(audio_path).read_bytes()).hexdigest()}

def require_cache(proof, context, audio_path):
    if not isinstance(proof, dict) or proof != cache_proof(context, audio_path):
        raise ValueError('Voice cache lacks exact V4 context/audio proof; preserve history and reconcile before reuse or regeneration')

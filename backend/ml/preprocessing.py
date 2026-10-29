"""Conservative, versioned NLP; preserves original text and negation."""
import re
import unicodedata

VERSION = 'villa-nlp-v1'
# Explicit vocabulary corrections only. Do not fuzzy-correct names or unknown Tagalog.
CORRECTIONS = {
    'drrty': 'dirty', 'poool': 'pool', 'mahinaa': 'mahina',
    'slooow': 'slow', 'gud': 'good', 'cozyness': 'coziness',
    'wekens': 'weakens', 'airconditioning': 'air conditioning',
    'aircondition': 'air conditioning', 'wifi': 'wi-fi',
}


def normalize(text):
    text = unicodedata.normalize('NFKC', str(text)).casefold().replace('’', "'")
    text = re.sub(r"\b[\w-]+\b", lambda m: CORRECTIONS.get(m.group(), m.group()), text)
    return re.sub(r'\s+', ' ', text).strip()


def phrases(text):
    # Preserve clause evidence. Splitting is deliberately conservative: no arbitrary
    # translation or implied subject propagation to an unrelated facility.
    clauses = re.split(r'[.!?;\n•]+|\b(?:but|pero|however|although)\b|,\s*(?=(?:the|ang|mahina|mabait|madumi|weak|slow|friendly|dirty|clean|staff|pool|aircon)\b)|\band\s+(?=(?:the|ang|mahina|mabait|madumi)\b)', str(text), flags=re.I)
    return [{'text': part.strip(' ,:-\t'), 'normalized': normalize(part.strip(' ,:-\t'))}
            for part in clauses if len(part.strip(' ,:-\t')) >= 3][:80]

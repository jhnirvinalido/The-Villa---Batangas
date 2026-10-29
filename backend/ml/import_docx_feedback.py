"""Extract review text from the supplied Google-review DOCX; no rating inference."""
import argparse
import csv
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
HEADER = re.compile(r'^(?:Local Guide\s*·\s*)?\d[\d,]* reviews?(?:\s*·.*)?$')
DATE = re.compile(r'^(?:[\ue000-\uf8ff]+\s*)?(?:Edited\s+)?(?:a|an|\d+)\s+(?:year|month|week|day|hour|minute)s?\s+ago$')
METADATA = re.compile(r'^(?:Rooms|Service|Location):\s*\d|^(?:Trip type|Travel group|Hotel highlights|Vacation|Couple|Family|Great value)$')

def extract_reviews(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    lines = [''.join(node.text or '' for node in paragraph.findall('.//w:t', NS)).strip()
             for paragraph in root.findall('.//w:p', NS)]
    lines = [line for line in lines if line]
    headers = [i for i, line in enumerate(lines) if HEADER.fullmatch(line)]
    records = []
    seen = set()
    for number, header in enumerate(headers, 1):
        boundary = headers[number] - 1 if number < len(headers) else len(lines)
        date_index = next((i for i in range(header + 1, boundary) if DATE.fullmatch(lines[i])), None)
        if date_index is None:
            continue
        body = [line for line in lines[date_index + 1:boundary] if not METADATA.search(line)]
        # Two pasted reviewer headings were joined to review text in this source.
        # The first is duplicated next-review text; the second completes this review.
        if boundary < len(lines) and ':)Angeline Delemos' in lines[boundary]:
            body.append(lines[boundary].removesuffix('Angeline Delemos'))
        text = '\n'.join(body).strip()
        if not text:
            continue
        identity = re.sub(r'\s+', ' ', text.casefold()).strip()
        if identity in seen:
            continue
        seen.add(identity)
        records.append({'Review ID': f'docx-google-{number:03}', 'Guest Group': f'docx-google-{number:03}',
                        'Guest Feedback (Verbatim)': text, 'Sentiment Label': '',
                        'Annotation Status': 'unlabeled', 'Source': Path(path).name,
                        'Review Date Label': re.sub(r'^[\ue000-\uf8ff]+', '', lines[date_index]),
                        'Source Truncated': str('…' in text).lower()})
    return records, len(headers)


def export_reviews(source, destination):
    records, total = extract_reviews(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    return {'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'review_sections': total, 'text_reviews': len(records), 'excluded_without_text': total-len(records)}

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source', type=Path); parser.add_argument('output', type=Path)
    args=parser.parse_args()
    print(export_reviews(args.source,args.output))

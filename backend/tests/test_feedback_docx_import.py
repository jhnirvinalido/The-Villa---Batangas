"""Synthetic DOCX extraction fixtures; never used as training reviews."""
import csv
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from ml.import_docx_feedback import extract_reviews, export_reviews, NS

class FeedbackDocxImportTests(unittest.TestCase):
    def document(self, path, lines):
        uri=NS['w']
        root=ET.Element(f'{{{uri}}}document')
        body=ET.SubElement(root,f'{{{uri}}}body')
        for text in lines:
            paragraph=ET.SubElement(body,f'{{{uri}}}p')
            run=ET.SubElement(paragraph,f'{{{uri}}}r')
            ET.SubElement(run,f'{{{uri}}}t').text=text
        with ZipFile(path,'w') as archive:archive.writestr('word/document.xml',ET.tostring(root))

    def test_excludes_names_ratings_and_rating_only_entries_without_inventing_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'reviews.docx'
            self.document(source,['Reviewer One','2 reviews','\ue5d4','\ue838\ue8385 months ago','The staff were helpful.', 'Reviewer Two','Local Guide · 10 reviews · 2 photos','\ue5d4','\ue838Edited a year ago','Rooms: 5','Service: 4','Location: 5'])
            records,total=extract_reviews(source)
            self.assertEqual(total,2)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['Guest Feedback (Verbatim)'],'The staff were helpful.')
            self.assertEqual(records[0]['Sentiment Label'],'')
            self.assertEqual(records[0]['Review Date Label'],'5 months ago')
            self.assertNotIn('Reviewer One',str(records))
            report=export_reviews(source,Path(directory)/'dataset.csv')
            self.assertEqual(report['excluded_without_text'],1)

    def test_duplicate_review_text_is_not_imported_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'reviews.docx'
            self.document(source,['Guest A','1 review','\ue838a year ago','A peaceful stay.', 'Guest B','1 review','\ue8382 years ago','A peaceful stay.'])
            records,total=extract_reviews(source)
            self.assertEqual(total,2)
            self.assertEqual(len(records),1)

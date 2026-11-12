import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import notes_alerts as N  # noqa: E402

DOC = """<html><body><p>Table of contents</p><p>Notes to Consolidated Financial Statements 45</p>
<p>Item 8. Financial Statements</p><p>NOTES TO CONSOLIDATED FINANCIAL STATEMENTS</p>
<p>Note 12. Commitments and Contingencies</p>
<p>On March 3, 2026, the Company received a waiver from its lenders for the breach of the leverage covenant under its revolving credit facility.</p>
<p>""" + "Routine text. " * 300 + """</p>
<p>Item 9. Changes in and Disagreements with Accountants</p><p>Nothing here.</p></body></html>"""


class NotesAlertsTest(unittest.TestCase):
    def test_notes_section_skips_contents(self):
        n = N.notes_section(N.text_of(DOC))
        self.assertTrue(n.startswith("NOTES TO CONSOLIDATED"))
        self.assertIn("waiver from its lenders", n)
        self.assertNotIn("Changes in and Disagreements", n)

    def test_only_quoted_points_survive(self):
        n = N.notes_section(N.text_of(DOC))
        pts = [
            {"point": "Lenders waived a breach of the leverage covenant in March 2026.", "topic": "debt",
             "quote": "On March 3, 2026, the Company received a waiver from its lenders for the breach of the leverage covenant under its revolving credit facility."},
            {"point": "The company faces a fraud investigation.", "topic": "litigation",
             "quote": "The Company is the subject of an investigation by the Department of Justice into its accounting."},
        ]
        v = N.verified(pts, n)
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0]["topic"], "debt")

    def test_quote_marks_and_spacing_dont_matter(self):
        v = N.verified([{"point": "x happened.", "quote": "the Company’s   lenders granted a waiver of the covenant breach in full"}],
                       "In 2026 the Company's lenders granted a waiver of the covenant breach in full.")
        self.assertEqual(len(v), 1)


if __name__ == "__main__":
    unittest.main()

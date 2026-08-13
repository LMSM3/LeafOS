import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'core'/'python'))
import leaf_monday_report as report
from leaf_live_report import render_report
class MondayReportTests(unittest.TestCase):
 def test_heatmap_has_16_channels_and_slices(self):
  matrix=report.heatmap([{'event':'brain.plan','data':{'generation_tokens_per_second':0.5}}])
  self.assertEqual((16,16),(len(matrix),len(matrix[0])))
  self.assertEqual(1.0,matrix[4][-1])
 def test_html_is_read_only_projection(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'journal.lje').write_text('{"event":"checkpoint.valid","data":{}}\n',encoding='utf-8')
   out=render_report(root)
   self.assertIn('Read-only derived view',out.read_text(encoding='utf-8'))
 def test_missing_chrome_blocks_pdf(self):
  with tempfile.TemporaryDirectory() as d:
   original=report.chrome;report.chrome=lambda:None
   try:
    with self.assertRaises(RuntimeError):report.report_once(Path(d),False)
   finally:report.chrome=original
if __name__=='__main__':unittest.main()

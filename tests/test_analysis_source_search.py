"""Search the pinned Git source without exporting unrelated text files."""
import unittest
from unittest.mock import patch

import test_ai_extract
import analysis_run


class LiteralSearch(unittest.TestCase):
    setUp = test_ai_extract.Analysis.setUp
    git = test_ai_extract.Analysis.git

    def test_cold_search_decodes_only_eligible_candidates_and_keeps_original_lines(self):
        filename = 'odd*name.unknown'
        (self.repo/filename).write_bytes('header\rfirst needle\u2028second needle\n'.encode())
        (self.repo/'.env').write_text('needle')
        for index in range(16):
            (self.repo/f'other{index}.unknown').write_text(f'unrelated {index}')
        self.git('add','-f','.')
        self.git('commit','-qm','Pinned literal search')
        commit = self.git('rev-parse','HEAD').strip()
        with patch.object(analysis_run,'_blob_lines',wraps=analysis_run._blob_lines) as read:
            units = analysis_run._needed(str(self.repo),commit,[{'query':'needle'}],None,None,{}, {})
        hits = [(u['value']['file'],line['line'],line['text'])
                for u in units if u['kind']=='source' for line in u['value']['lines']]
        self.assertEqual(hits,[(filename,2,'first needle'),(filename,3,'second needle')])
        self.assertEqual(read.call_count,1)
        self.assertEqual(units[0]['value']['value']['total'],2)


if __name__=='__main__':
    unittest.main()

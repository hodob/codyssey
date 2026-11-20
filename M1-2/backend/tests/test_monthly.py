import unittest
from unittest import mock

from services import monthly
from services import repository as repo
from tests.fake_db import FakeDB

SAMPLE = '''"----- header -----"
"Year, Month, Excel, Date, CO2, ..."
1958,   1, 21200, 1958.0411,  -99.99, -99.99, -99.99, -99.99, 315.71, 314.43, MLO
2026,   8, 46250, 2026.6, 427.30, 424.0, 427.1, 424.0, 427.30, 424.0, MLO
2026,   9, 46281, 2026.7, 425.61, 424.1, 425.5, 424.1, 425.61, 424.1, MLO
2026,  10, 46311, 2026.8, 426.40, 424.2, 426.0, 424.2, 426.40, 424.2, MKO
2026,  11, 46342, 2026.9, -99.99, -99.99, -99.99, -99.99, -99.99, -99.99, MLO
'''


class ParseTest(unittest.TestCase):
    def test_parse_uses_observed_co2_only(self):
        rows = monthly.parse(SAMPLE)
        self.assertEqual([r["id"] for r in rows], ["mlo-2026-08", "mlo-2026-09", "mlo-2026-10"])
        self.assertEqual(rows[0], {"id": "mlo-2026-08", "date": "2026-08-15", "value": 427.3, "memo": "MLO"})
        self.assertEqual(rows[-1]["memo"], "MKO")


class RefreshTest(unittest.TestCase):
    def setUp(self):
        repo.clear_cache()
        monthly._last["at"] = None
        self.db = FakeDB()
        col = self.db.collection("data")
        col.document("mlo-2026-08").set({"date": "2026-08-15", "value": 427.3, "memo": "MLO"})
        col.document("custom1").set({"date": "2026-09-15", "value": 999.0, "memo": "내가 넣은 값"})  # 같은 달 수동 데이터

    def test_adds_only_new_months_and_never_overwrites(self):
        with mock.patch.object(monthly, "fetch", return_value=SAMPLE):
            out = monthly.refresh(self.db)
        self.assertEqual(out["added_months"], ["2026-10"])      # 08 은 이미 있고, 09 는 수동 데이터가 있어 건너뜀
        self.assertEqual(out["source_latest"], "2026-10")
        self.assertEqual(self.db.collection("data").document("custom1").get().to_dict()["value"], 999.0)
        self.assertEqual(len(repo.list_data(self.db)), 3)       # 캐시가 무효화되어 새 문서가 보임

    def test_cooldown_blocks_rapid_calls(self):
        with mock.patch.object(monthly, "fetch", return_value=SAMPLE):
            monthly.refresh(self.db)
            with self.assertRaises(monthly.Cooldown) as cm:
                monthly.refresh(self.db)
        self.assertGreater(cm.exception.remaining, 0)

    def test_source_failure(self):
        with mock.patch.object(monthly, "fetch", side_effect=monthly.SourceUnavailable("x")):
            with self.assertRaises(monthly.SourceUnavailable):
                monthly.refresh(self.db)
        monthly._last["at"] = None
        with mock.patch.object(monthly, "fetch", return_value="garbage"):
            with self.assertRaises(monthly.SourceUnavailable):
                monthly.refresh(self.db)


if __name__ == "__main__":
    unittest.main()

"""core/catalog — venue 로딩과 정합 검증.

실행: 저장소 루트에서  python3 -m unittest discover -s tests -t .

테스트는 자기가 쓸 데이터를 스스로 만든다. 프로덕션 파일에 기대면 (a) 데이터가 바뀔 때 테스트가
깨지고 (b) 파일이 없는 환경에선 못 돌고 (c) 읽어도 무엇을 검사하는지 알 수 없다. 그래서 아래
합성 카탈로그·정책은 테스트 안에 그대로 적혀 있다. 프로덕션 파일과 맞물리는 것은 맨 끝
RealFilesTest 뿐이고, 그건 일부러 그렇다 — "누가 motions.yaml 을 고쳐 venue 를 깨뜨렸나" 를
잡으려는 테스트이기 때문이다.
"""

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from core import catalog
from core.catalog import FATAL, WARN, VenueError, load_venue, validate

ROOT = Path(__file__).resolve().parent.parent

# 패드는 4×3 = 12칸이다. 깨끗한 venue 는 12칸을 채워야 한다 — 12칸이 아니면 WARN 이 나오는 게
# 맞고, 그건 test_pad_grid_size 가 따로 검사한다. 여기서 2칸짜리를 "깨끗하다" 고 하면 모든 테스트에
# 그 경고가 섞여 무엇이 무엇을 검사하는지 안 보인다.
PAD12 = ["MimicWave", "MimicBow"] + [f"MimicPad{i:02d}" for i in range(10)]
CATALOG = {
    "motions": [{"state": m} for m in PAD12 + ["MimicDance", "MimicNotAllowed"]],
    "control_states": [{"state": "Velocity"}],
}
POLICY = {"api_allowlist": PAD12 + ["MimicDance", "Velocity"]}   # MimicNotAllowed 만 빠져 있다


def good_venue(**over):
    v = {"pad_grid": list(PAD12),
         "presets": {"song-api": {"motion": "MimicDance", "media": "song.mp4",
                                  "offset_ms": -1500, "media_len_sec": 30}}}
    v.update(over)
    return v


def levels(problems):
    return sorted((p.level, p.where.split(" ")[0]) for p in problems)


class ValidateTest(unittest.TestCase):
    def test_clean_venue_has_no_problems(self):
        self.assertEqual(validate(CATALOG, POLICY, good_venue(), require_media=False), [])

    def test_preset_motion_missing_from_catalog_is_fatal(self):
        """8/21: 영상은 A, 로봇은 B. 프리셋이 가리키는 동작이 아예 없으면 무대가 시작 못 한다.

        MimicGhost 는 허용목록엔 있고 카탈로그엔 없다 — 그래야 "카탈로그에 없다" 분기만 따로
        시험된다. 허용목록에도 없는 동작으론 다른 분기가 대신 잡아 줘서, 이 검사를 통째로
        지워도 테스트가 통과했다 (변이 테스트로 확인)."""
        policy = {"api_allowlist": POLICY["api_allowlist"] + ["MimicGhost"]}
        v = good_venue(presets={"x": {"motion": "MimicGhost"}})
        out = validate(CATALOG, policy, v)
        self.assertEqual(levels(out), [(FATAL, "presets.x")])
        self.assertIn("카탈로그에 없다", out[0].msg)

    def test_preset_motion_absent_everywhere_is_fatal(self):
        v = good_venue(presets={"x": {"motion": "MimicNope"}})
        self.assertEqual(levels(validate(CATALOG, POLICY, v)), [(FATAL, "presets.x")])

    def test_preset_motion_not_in_api_allowlist_is_fatal(self):
        """카탈로그엔 있어도 api_allowlist 에 없으면 로봇이 무대 시작 뒤에 조용히 거부한다."""
        v = good_venue(presets={"x": {"motion": "MimicNotAllowed"}})
        out = validate(CATALOG, POLICY, v)
        self.assertEqual(levels(out), [(FATAL, "presets.x")])
        self.assertIn("api_allowlist", out[0].msg)

    def test_pad_grid_item_not_in_catalog_or_allowlist_is_fatal(self):
        for bad in ("MimicNope", "MimicNotAllowed"):
            with self.subTest(bad):
                out = validate(CATALOG, POLICY, good_venue(pad_grid=PAD12[:11] + [bad]))
                self.assertEqual([p.level for p in out], [FATAL])
                self.assertIn("pad_grid[12]", out[0].where)

    def test_pad_grid_missing_or_empty_is_fatal(self):
        for grid in (None, [], "MimicWave"):
            with self.subTest(repr(grid)):
                out = validate(CATALOG, POLICY, good_venue(pad_grid=grid), require_media=False)
                self.assertIn((FATAL, "venue.pad_grid"), levels(out))

    def test_non_numeric_preset_field_is_fatal(self):
        """손으로 고치다 "-1500" 처럼 문자열이 되면 서버는 float() 에서 죽거나 0 으로 읽는다."""
        v = good_venue(presets={"x": {"motion": "MimicWave", "offset_ms": "-1500"}})
        out = validate(CATALOG, POLICY, v)
        self.assertEqual([(p.level, p.where) for p in out], [(FATAL, "presets.x")])
        self.assertIn("offset_ms", out[0].msg)

    def test_bool_is_not_a_number(self):
        v = good_venue(presets={"x": {"motion": "MimicWave", "volume": True}})
        self.assertEqual([p.level for p in validate(CATALOG, POLICY, v)], [FATAL])

    def test_missing_media_is_fatal_on_stage_but_only_warn_for_dev(self):
        with tempfile.TemporaryDirectory() as media:
            stage = validate(CATALOG, POLICY, good_venue(), media_dir=media, require_media=True)
            dev = validate(CATALOG, POLICY, good_venue(), media_dir=media, require_media=False)
        self.assertEqual([p.level for p in stage], [FATAL])
        self.assertEqual([p.level for p in dev], [WARN])   # 없다는 사실은 여전히 보인다

    def test_existing_media_passes(self):
        with tempfile.TemporaryDirectory() as media:
            (Path(media) / "song.mp4").touch()
            self.assertEqual(validate(CATALOG, POLICY, good_venue(), media_dir=media), [])

    def test_missing_media_len_sec_warns(self):
        """없으면 무대 자동종료가 기본 60초로 떨어져 84초짜리 무대가 곡 중간에 끊긴다 (2026-08-18)."""
        v = good_venue(presets={"x": {"motion": "MimicWave", "media": "m.mp4"}})
        out = validate(CATALOG, POLICY, v)
        self.assertEqual([(p.level, p.where) for p in out], [(WARN, "presets.x")])
        self.assertIn("media_len_sec", out[0].msg)

    def test_motion_only_preset_needs_no_media_len(self):
        v = good_venue(presets={"x": {"motion": "MimicWave"}})
        self.assertEqual(validate(CATALOG, POLICY, v), [])

    def test_missing_clip_warns_only(self):
        with tempfile.TemporaryDirectory() as clips:
            for m in PAD12[:11]:
                (Path(clips) / f"{m}.mp4").touch()
            out = validate(CATALOG, POLICY, good_venue(), clips_dir=clips)
        self.assertEqual([(p.level, p.where.split()[1]) for p in out], [(WARN, PAD12[11])])

    def test_duplicate_pad_item_warns(self):
        out = validate(CATALOG, POLICY, good_venue(pad_grid=PAD12[:11] + [PAD12[0]]))
        self.assertEqual([(p.level, "두 번" in p.msg) for p in out], [(WARN, True)])

    def test_pad_grid_size(self):
        """4×3 = 12칸. 그 밖이면 칸이 넘치거나 비어서 화면이 어긋난다 — 막지는 않고 알린다(테마마다 다를 수 있다)."""
        for grid in (PAD12[:11], PAD12 + ["MimicDance"]):
            with self.subTest(len(grid)):
                out = validate(CATALOG, POLICY, good_venue(pad_grid=grid))
                self.assertEqual([(p.level, p.where) for p in out], [(WARN, "venue.pad_grid")])

    def test_rc_dial_duplicate_warns(self):
        doc = dict(CATALOG, rc_list={"banks": {
            "A": {"slots": [{"slot": 200, "state": "MimicWave"}, {"slot": 200, "state": "MimicBow"}]},
            "B": {"slots": [{"slot": 200, "state": "MimicWave"}]}}})
        out = validate(doc, POLICY, good_venue(), require_media=False)
        self.assertEqual({p.level for p in out}, {WARN})
        text = " ".join(p.msg for p in out)
        self.assertIn("A:200", text)          # 같은 동작이 두 자리
        self.assertIn("겹친다", text)          # 한 뱅크에서 슬롯 번호가 겹침

    def test_never_raises_on_garbage_preset(self):
        v = good_venue(presets={"a": "not a dict", "b": None})
        out = validate(CATALOG, POLICY, v)
        self.assertEqual([p.level for p in out], [FATAL, FATAL])


class LoadVenueTest(unittest.TestCase):
    def make(self, tmp, venue_yaml=None, presets_json=None):
        d = Path(tmp) / "v"; d.mkdir()
        if venue_yaml is not None:
            (d / "venue.yaml").write_text(venue_yaml, encoding="utf-8")
        if presets_json is not None:
            (d / "presets.json").write_text(presets_json, encoding="utf-8")
        return d

    def test_reads_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, "name: 시험\npad_grid: [MimicWave]\nnotes: 메모\n",
                          json.dumps({"p": {"motion": "MimicWave"}}))
            v = load_venue(d)
        self.assertEqual((v["name"], v["pad_grid"], v["notes"]), ("시험", ["MimicWave"], "메모"))
        self.assertEqual(v["presets"], {"p": {"motion": "MimicWave"}})

    def test_presets_file_is_optional(self):
        """새 행사 폴더는 프리셋이 없이 시작한다. /dance 에서 저장하면 그때 생긴다."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_venue(self.make(tmp, "pad_grid: [MimicWave]\n"))["presets"], {})

    def test_name_falls_back_to_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_venue(self.make(tmp, "pad_grid: []\n"))["name"], "v")

    def test_missing_venue_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VenueError):
                load_venue(self.make(tmp, presets_json="{}"))

    def test_broken_files_raise_instead_of_returning_empty(self):
        """깨진 파일을 빈 값으로 읽으면 패드 0칸으로 조용히 뜬다. 시끄럽게 죽어야 한다."""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VenueError):
                load_venue(self.make(tmp, "pad_grid: [unclosed\n"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VenueError):
                load_venue(self.make(tmp, "pad_grid: []\n", "{not json"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(VenueError):
                load_venue(self.make(tmp, "- a list\n- not a mapping\n"))


class RealFilesTest(unittest.TestCase):
    """프로덕션 파일과 맞물리는 유일한 곳. 일부러 그렇다 — motions.yaml 이나 정책을 고치다가
    venue 를 깨뜨리는 사고를 커밋 전에 잡는다."""

    @classmethod
    def setUpClass(cls):
        cls.cat = yaml.safe_load((ROOT / "solo_stage" / "motions.yaml").read_text())
        cls.policy = yaml.safe_load((ROOT / "solo_stage" / "gateway_config.yaml").read_text())["policy"]

    def test_every_venue_in_repo_has_no_fatal(self):
        venues = sorted(p for p in (ROOT / "config" / "venues").iterdir() if p.is_dir())
        self.assertTrue(venues, "venue 가 하나도 없다")
        for d in venues:
            with self.subTest(d.name):
                bad = [str(p) for p in validate(self.cat, self.policy, load_venue(d), require_media=False)
                       if p.level == FATAL]
                self.assertEqual(bad, [])

    def test_default_pad_grid_is_the_twelve_from_the_opening(self):
        """정책에서 venue 로 옮긴 목록. 순서까지 8/18 사용자 확정본과 같아야 한다."""
        grid = load_venue(ROOT / "config" / "venues" / "default")["pad_grid"]
        self.assertEqual(len(grid), 12)
        self.assertEqual(grid[0], "MimicBowNavel")
        self.assertEqual(grid[-1], "MimicGuapVer2")

    def test_policy_no_longer_carries_pad_allowlist(self):
        """두 곳에 있으면 어느 쪽이 이기는지 아무도 모른다."""
        self.assertNotIn("pad_allowlist", self.policy)

    def test_apps_share_identical_catalog_and_policy(self):
        """앱 폴더에 남긴 사본(로봇에 평평하게 배포돼서 못 옮겼다)이 갈라지면 드리프트다."""
        for name in ("motions.yaml", "gateway_config.yaml"):
            with self.subTest(name):
                self.assertEqual((ROOT / "solo_stage" / name).read_bytes(),
                                 (ROOT / "group_stage" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()

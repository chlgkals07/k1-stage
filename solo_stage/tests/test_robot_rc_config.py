import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


TOOL = Path(__file__).parent.parent / "tools" / "verify_robot_rc_config.py"
SPEC = importlib.util.spec_from_file_location("verify_robot_rc_config", TOOL)
verify_robot_rc_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_robot_rc_config)


class RobotRcConfigTest(unittest.TestCase):
    def setUp(self):
        self.motions = yaml.safe_load((Path(__file__).parent.parent / "motions.yaml").read_text())
        self.config = {"selectors": {}}
        for bank, selector in verify_robot_rc_config.SELECTOR_KEY.items():
            slots = self.motions["rc_list"]["banks"][bank]["slots"]
            self.config["selectors"][selector] = {
                "table": {item["slot"]: item["state"] for item in slots}}

    def test_current_rc_list_matches_equivalent_robot_backup(self):
        problems, checked = verify_robot_rc_config.verify(self.config, self.motions)
        self.assertEqual(problems, [])
        self.assertEqual(checked, 40)

    def test_guap_v1_is_a_blocking_failure(self):
        self.config["selectors"]["mimic_selector_b"]["table"][202] = "MimicGuap"
        problems, _ = verify_robot_rc_config.verify(self.config, self.motions)
        self.assertTrue(any("B-202" in problem for problem in problems))
        self.assertTrue(any("MimicGuapVer2" in problem for problem in problems))

    def test_missing_selector_is_reported_without_crash(self):
        del self.config["selectors"]["mimic_selector"]
        problems, checked = verify_robot_rc_config.verify(self.config, self.motions)
        self.assertIn("A: selectors.mimic_selector.table 을 찾지 못했습니다", problems)
        self.assertEqual(checked, 20)

    def test_cli_reads_a_backup_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "k1_config.yaml"
            original = yaml.safe_dump(self.config, allow_unicode=True)
            backup.write_text(original)
            code = verify_robot_rc_config.main(["verify", str(backup)])
            self.assertEqual(code, 0)
            self.assertEqual(backup.read_text(), original)


if __name__ == "__main__":
    unittest.main()

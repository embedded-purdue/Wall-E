"""Offline regression checks; no model downloads or credentials required."""
import csv
import json
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from bt_validator import BehaviorTreeValidator, BTValidationError
from summarize import tree_section
from walle_bt import SCHEMA, load_chat_model


class BaselineTests(unittest.TestCase):
    def run_script(self, *args, success=True):
        result = subprocess.run([sys.executable, *map(str, args)], cwd=Path(tempfile.gettempdir()),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_adapter_and_base_revisions_are_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = Path(tmp) / "adapter_config.json"
            adapter.write_text(json.dumps({"base_model_name_or_path": "base-model"}))
            hub = SimpleNamespace(
                model_info=MagicMock(side_effect=[
                    SimpleNamespace(sha="adapter-commit", siblings=[SimpleNamespace(rfilename="adapter_config.json")]),
                    SimpleNamespace(sha="base-commit")]),
                hf_hub_download=MagicMock(return_value=str(adapter)))
            model_class, tokenizer_class, peft = MagicMock(), MagicMock(), MagicMock()
            modules = {"torch": SimpleNamespace(float32="float32"),
                       "huggingface_hub": hub,
                       "transformers": SimpleNamespace(AutoModelForCausalLM=model_class,
                                                       AutoTokenizer=tokenizer_class),
                       "peft": SimpleNamespace(PeftModel=peft)}
            with patch.dict(sys.modules, modules):
                generate = load_chat_model("adapter-model", "cpu", "requested", "pinned-base")
            self.assertEqual(generate.metadata["revision"], "adapter-commit")
            self.assertEqual(generate.metadata["base_revision"], "base-commit")
            model_class.from_pretrained.assert_called_once_with(
                "base-model", torch_dtype="float32", revision="base-commit")
            self.assertEqual(peft.from_pretrained.call_args.kwargs["revision"], "adapter-commit")
            hub.model_info.assert_any_call("base-model", revision="pinned-base")

    def test_schema_rejects_wrong_node_kind_and_ports(self):
        validator = BehaviorTreeValidator.from_yaml(SCHEMA)
        for leaf in ['<Action ID="IsVisible" object="ball"/>', '<Release object="ball"/>']:
            with self.assertRaises(BTValidationError):
                validator.validate(f'<root BTCPP_format="4"><BehaviorTree ID="MainTree">{leaf}</BehaviorTree></root>')
        self.assertEqual((HERE.parent / "wall_e.yaml").resolve(), SCHEMA)

    def test_mock_runs_resume_and_keep_models_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            trees = Path(tmp) / "trees.csv"
            command = [HERE / "run_tree_baseline.py", "--mock", "--out", trees]
            self.run_script(*command)
            rows = list(csv.DictReader(io.StringIO(trees.read_text())))
            self.assertEqual(len(rows), 196)
            self.assertTrue(all(row["valid"] == "y" for row in rows))
            self.assertTrue(all(row["matches_reference"] == "y" for row in rows))
            self.assertTrue(all(row["model"].startswith("mock:") for row in rows))
            self.assertTrue(all(not row["does_what_was_asked"] for row in rows))
            before = trees.read_bytes()
            self.run_script(*command, "--resume")
            self.assertEqual(before, trees.read_bytes())
            self.run_script(*command, "--resume", "--seed", "99", success=False)
            self.run_script(*command, success=False)
            lines = tree_section(trees)
            self.assertEqual(sum(line.startswith("| mock:") for line in lines), 4)
            self.assertTrue(any("Pending" in line for line in lines))
            classifier = Path(tmp) / "classifier.csv"
            self.run_script(HERE / "run_classifier.py", "--mock", "--out", classifier)
            classified = list(csv.DictReader(io.StringIO(classifier.read_text())))
            self.assertEqual(len(classified), 91)
            self.assertTrue(all(row["json_ok"] == "y" for row in classified))
            self.assertTrue(Path(str(classifier) + ".meta.json").exists())

    def test_seed_export_and_leakage_rejection(self):
        training = SCHEMA.parents[2] / "training/walle"
        sys.path.insert(0, str(training))
        from build_data import build
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "data"
            manifest = build(out)
            self.assertEqual(manifest["counts"], {"tree_train": 11, "tree_validation": 2,
                                                  "main_train": 20, "main_validation": 4})
            self.assertEqual(manifest["near_duplicate_warnings"], [])
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            build(out)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
            seeds = json.loads((training / "tree_seeds.json").read_text())
            seeds[0]["request"] = "Go to the ball"
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(seeds))
            with self.assertRaisesRegex(ValueError, "leakage"):
                build(out, tree_source=bad)
            seeds[0]["request"] = "A unique candidate request"
            seeds[0]["tree_xml"] = seeds[0]["tree_xml"].replace('object="toy car"', 'object="{object}"')
            bad.write_text(json.dumps(seeds))
            with self.assertRaisesRegex(ValueError, "placeholder"):
                build(out, tree_source=bad)


if __name__ == "__main__":
    unittest.main()

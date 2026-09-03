import tempfile
import tomllib
import unittest
from pathlib import Path

from scripts.reconcile import reconcile_file


class ReconcileTests(unittest.TestCase):
    def test_merge_preserves_local_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.toml"
            destination = root / "destination.toml"
            source.write_text('[features]\nfoo = true\n')
            destination.write_text(
                '[projects."/machine-only"]\ntrust_level = "trusted"\n'
                '\n[features]\nfoo = false\nbar = "local"\n'
            )

            reconcile_file(source, destination)

            result = destination.read_text()
            self.assertIn('[projects."/machine-only"]', result)
            self.assertIn('foo = true', result)
            self.assertIn('bar = "local"', result)

    def test_merge_repairs_multiline_inline_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.toml"
            destination = root / "destination.toml"
            source.write_text('[features]\nfoo = true\n')
            destination.write_text(
                '[otel]\nexporter = { otlp-grpc = {\n'
                '  endpoint = "http://localhost:4317"\n} }\n'
            )

            reconcile_file(source, destination)

            self.assertEqual(
                "http://localhost:4317",
                tomllib.loads(destination.read_text())["otel"]["exporter"][
                    "otlp-grpc"
                ]["endpoint"],
            )


if __name__ == "__main__":
    unittest.main()

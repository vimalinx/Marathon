from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import host.model_env as model_env


class LoadModelEnvDefaultsTests(unittest.TestCase):
    def test_load_model_env_defaults_only_fills_missing_values(self) -> None:
        with TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / "model.env"
            env_file.write_text(
                "\n".join(
                    [
                        "export MARATHON_BASE_URL=https://example.com/v1",
                        "export MARATHON_API_KEY=test-key",
                        "export MARATHON_MODEL=gpt-5.4",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            environ = {"MARATHON_MODEL": "already-set"}

            loaded = model_env.load_model_env_defaults(environ, env_file=env_file)

        self.assertEqual(environ["MARATHON_MODEL"], "already-set")
        self.assertEqual(environ["MARATHON_BASE_URL"], "https://example.com/v1")
        self.assertEqual(environ["MARATHON_API_KEY"], "test-key")
        self.assertEqual(loaded["MARATHON_BASE_URL"], "https://example.com/v1")
        self.assertEqual(loaded["MARATHON_API_KEY"], "test-key")
        self.assertNotIn("MARATHON_MODEL", loaded)


if __name__ == "__main__":
    unittest.main()

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import container.agent_tools as agent_tools


class ResolveCwdTests(unittest.TestCase):
    def test_resolve_cwd_uses_marathon_sandbox_env(self) -> None:
        with TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir) / "sandbox"
            sandbox.mkdir()
            with mock.patch.dict(os.environ, {"MARATHON_SANDBOX": str(sandbox)}, clear=False):
                self.assertEqual(agent_tools.resolve_cwd(), sandbox)


if __name__ == "__main__":
    unittest.main()

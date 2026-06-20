"""The test that backs task T001 in the worked example.

verify_core runs this file as a subprocess and treats a green exit code as the
tests-pass evidence for T001. It imports the demo source by relative path so the
example needs no install.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from greeter import greet  # noqa: E402


def test_greet_uses_the_name():
    assert greet("Mergen") == "Hello, Mergen."

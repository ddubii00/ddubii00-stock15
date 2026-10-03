import importlib.util
from pathlib import Path


def test_source_private_file_and_browser_storage_scan():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('security_check', root / 'scripts/security_check.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    assert checker.check() == 0

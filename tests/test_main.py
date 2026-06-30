import importlib


def test_main_module_imports():
    module = importlib.import_module("bioops.main")
    assert hasattr(module, "main")

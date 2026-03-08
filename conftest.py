import sys
import os

# Add src/ so `import rolemesh` works as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Pre-import all submodules so relative imports resolve correctly,
# then alias them so bare imports (from registry_client import ...) still work in tests
import importlib

_submodules = [
    "init_db", "registry_client", "amp_caller", "symphony_fusion",
    "queue_worker", "message_worker", "autoevo_worker",
    "installer", "contracts", "round_reporter",
]

for _name in _submodules:
    try:
        _mod = importlib.import_module(f"rolemesh.{_name}")
        sys.modules.setdefault(_name, _mod)
    except Exception:
        pass

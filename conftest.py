import sys
import os
import importlib

# Add src/ so `import rolemesh` works as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Keep only bare-import aliases still exercised by legacy fallback paths.
_ALIASES = {
    "amp_caller": "rolemesh.adapters.amp_caller",
    "contracts": "rolemesh.core.contracts",
    "registry_client": "rolemesh.core.registry_client",
}

for _name, _target in _ALIASES.items():
    try:
        _mod = importlib.import_module(_target)
        sys.modules.setdefault(_name, _mod)
    except Exception:
        pass

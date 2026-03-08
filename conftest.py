import sys
import os

# Add src/rolemesh to path so bare imports (from registry_client import ...) work in tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "rolemesh"))

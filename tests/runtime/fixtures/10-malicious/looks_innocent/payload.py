"""Sentinel side-effect: running this means inspect executed setup code.

Even importing the package marker should NOT execute this — the runtime
must only ast.parse, never exec / import.
"""
import subprocess
import sys

subprocess.run([sys.executable, "-c", "open('/tmp/INSPECT_EXECUTED_REPO_CODE', 'w').write('owned')"],
               check=False)

"""Sentinel side-effect: creating this file means inspect imported this module.

If you ever see /tmp/INSPECT_IMPORTED_A_REPO_MODULE in a test
environment, the inspect pipeline has regressed.
"""
import os

with open("/tmp/INSPECT_IMPORTED_A_REPO_MODULE", "w", encoding="utf-8") as _fh:
    _fh.write("owned: inspect imported a repo module\n")

# Reguard Core v0.1 — Python Namespace Collision Audit

**Date:** 2026-08-30
**Verdict:** **NO_COLLISION**
**Decision:** `RENAME_REQUIRED_BEFORE_RELEASE = FALSE`

The Reguard wheel installs a top-level `compliance` Python package,
but there is **no real collision** with any other PyPI distribution:

- The only other PyPI distribution named `compliance` is
  `compliance-0.0.0`, which is a placeholder distribution that
  installs a single flat file `script.py` (not a package).
- `compliance-0.0.0` owns **zero** `compliance/` package files.
- Reguard owns the entire `compliance/` package directory tree.
- Both can coexist in the same `site-packages` without Reguard's
  imports resolving incorrectly.

---

## 1.1 Inspect ownership

**Wheel contents of `dist/reguard-0.1.0rc1-py3-none-any.whl`:**

```
top_level.txt: compliance
top-level entries in wheel: ['compliance', 'reguard-0.1.0rc1.dist-info']
entry_points.txt:
  [console_scripts]
  reguard = compliance.cli.main:main
```

Confirmed: the public import namespace for Reguard is
`import compliance`.

## 1.2 Existing PyPI `compliance` distribution

The currently-published `compliance-0.0.0` wheel
(`https://pypi.org/project/compliance/`) was downloaded for
inspection in a **disposable venv only** — the Reguard environment
was not modified:

```text
$ pip download compliance --no-deps -d /tmp/compliance-download
Successfully downloaded compliance-0.0.0-py3-none-any.whl

$ python3 -c "import zipfile; z=zipfile.ZipFile('compliance-0.0.0-py3-none-any.whl'); \
    print(z.namelist())"
['script.py',
 'compliance-0.0.0.dist-info/METADATA',
 'compliance-0.0.0.dist-info/WHEEL',
 'compliance-0.0.0.dist-info/entry_points.txt',
 'compliance-0.0.0.dist-info/top_level.txt',
 'compliance-0.0.0.dist-info/RECORD']
```

The `compliance-0.0.0` wheel installs:

| File | Owned by |
|---|---|
| `script.py` (a flat module) | `compliance-0.0.0` |
| `compliance-0.0.0.dist-info/` | `compliance-0.0.0` |

**`compliance-0.0.0` does NOT install a `compliance/` package
directory.** It does not install `compliance/__init__.py` or any
submodule. The METADATA confirms:

```
Name: compliance
Version: 0.0.0
Summary: A simple script.
Author: fridex.devel@gmail.com
License: LGPLv3+
```

This is a single-file placeholder distribution, not a Python
package namespace.

## 1.3 Collision test

Two test venvs were created and the install order was reversed:

### Order 1: Reguard first, then `compliance-0.0.0`

```text
$ pip install dist/reguard-0.1.0rc1-py3-none-any.whl
Successfully installed reguard-0.1.0rc1

$ pip install compliance
Successfully installed compliance-0.0.0

$ reguard --version
reguard 0.1.0rc1

$ reguard doctor
doctor: OK

$ python3 -c "import compliance; print(compliance.__file__)"
/tmp/.../site-packages/compliance/__init__.py

$ python3 -c "from compliance.cli.main import main; print('OK')"
OK

$ ls site-packages/compliance/
__init__.py  adapters  cli  config.py  corpus  corpus_runner  db.py
integrations  legal  models.py  pipeline  requirements

$ ls site-packages/script.py
/tmp/.../site-packages/script.py
```

Reguard imports resolve correctly. `script.py` is installed
unambiguously as a flat module.

### Order 2: `compliance-0.0.0` first, then Reguard

```text
$ pip install compliance
Successfully installed compliance-0.0.0

$ pip install dist/reguard-0.1.0rc1-py3-none-any.whl
Successfully installed reguard-0.1.0rc1

$ reguard --version
reguard 0.1.0rc1

$ reguard check --repo-path /tmp/reverse-collision-demo ...
4 events, 2 framework artifact(s)
PASS
```

Same result. Both distributions coexist cleanly in both install
orders. Neither overwrites the other's files.

### Verdict on install interactions

| Question | Answer |
|---|---|
| Does Reguard install overwrite files owned by `compliance-0.0.0`? | No (no overlap) |
| Does `compliance-0.0.0` install overwrite files owned by Reguard? | No (no overlap) |
| Do the two namespaces merge accidentally? | No (separate file sets) |
| Is package ownership ambiguous? | No |
| Do Reguard imports resolve correctly? | Yes |
| Is the result harmless? | Yes — proven by both install orders |

## 1.4 Decision

```text
NO_COLLISION
```

No rename is required. The `compliance/` Python package namespace
is unambiguously owned by Reguard. The placeholder `compliance-0.0.0`
distribution owns a single unrelated flat file (`script.py`).

## Regression test

`tests/packaging/test_namespace_coexistence.py` was added with
4 regression tests that prove the wheel:

1. Declares a `compliance/` package directory.
2. Does not own `script.py` or `compliance.py` flat modules.
3. Has only `compliance/` and `<name>.dist-info/` as top-level
   entries.
4. Targets `compliance.cli.main:main` from the `reguard`
   console-script entry point.

If a future Reguard release accidentally starts shipping files
that other distributions claim, or stops shipping `compliance/`,
this test will fail before the artifact is published.

— end of namespace collision audit —
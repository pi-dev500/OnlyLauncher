"""Runtime hook: run ``portablemc_login.py`` inside the frozen binary.

``McOptions`` starts the Microsoft login window with
``[sys.executable, <dir>/portablemc_login.py, ...]``. Once frozen,
``sys.executable`` is the launcher itself, so that call would relaunch the
whole launcher instead of the Qt login window. This hook inspects
``sys.argv`` and, when the helper script is the target, executes it in the
current process (no second bootloader start, no extra extraction).
"""

import os
import sys

_HELPER = "portablemc_login.py"


def _is_helper_call(argv):
    """Return True when argv looks like ``<python> .../portablemc_login.py``."""
    for arg in argv[1:3]:
        if os.path.basename(str(arg)).lower() == _HELPER:
            return True
    return False


if getattr(sys, "frozen", False) and _is_helper_call(sys.argv):
    _here = os.path.dirname(os.path.abspath(__file__))
    _script = os.path.join(_here, _HELPER)
    # Keep argv[0] as the script path so the helper sees a normal __main__.
    sys.argv = [_script] + [a for a in sys.argv[1:]
                            if os.path.basename(str(a)).lower() != _HELPER]
    with open(_script, "r", encoding="utf-8") as _fh:
        _code = compile(_fh.read(), _script, "exec")
    _globals = {"__name__": "__main__", "__file__": _script,
                "__builtins__": __builtins__}
    exec(_code, _globals)  # noqa: S102 - trusted file bundled with the app
    sys.exit(0)

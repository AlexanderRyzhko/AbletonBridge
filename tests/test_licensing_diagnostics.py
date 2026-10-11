import importlib.util
from pathlib import Path


HANDLER_PATH = (
    Path(__file__).resolve().parents[1]
    / "AbletonBridge_Remote_Script"
    / "handlers"
    / "diagnostics.py"
)
SPEC = importlib.util.spec_from_file_location("licensing_diagnostics", HANDLER_PATH)
assert SPEC and SPEC.loader
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


class _Bridge:
    __module__ = "Live.Licensing"

    def save_current_set(self):
        raise AssertionError("diagnostic must never invoke Save")


class _Owner:
    __module__ = "abl.live.licensing"
    __name__ = "PythonLicensing"

    def __init__(self):
        self.licensing_bridge = _Bridge()


_Owner.__name__ = "PythonLicensing"


def test_describe_licensing_objects_finds_existing_owner_without_invocation():
    result = diagnostics._describe_licensing_objects([_Owner(), object()])

    assert result["owner_count"] == 1
    assert result["callable_save_owner_count"] == 1
    assert result["single_callable_owner"] is True
    assert result["mutation_performed"] is False
    assert result["bridge_types"] == ["Live.Licensing._Bridge"]


def test_describe_licensing_objects_reports_absence():
    result = diagnostics._describe_licensing_objects([object()])

    assert result["owner_count"] == 0
    assert result["callable_save_owner_count"] == 0
    assert result["single_callable_owner"] is False
    assert result["mutation_performed"] is False

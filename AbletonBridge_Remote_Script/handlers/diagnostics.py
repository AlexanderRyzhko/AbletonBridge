"""Read-only diagnostics for bounded Stable Live capability probes."""

from __future__ import absolute_import, print_function, unicode_literals

import gc
import sys


def _describe_licensing_objects(objects=None):
    """Describe existing licensing owners without constructing or invoking them."""
    if objects is None:
        objects = gc.get_objects()

    owners = []
    bridge_types = set()
    for obj in objects:
        obj_type = type(obj)
        if (
            getattr(obj_type, "__module__", "") != "abl.live.licensing"
            or getattr(obj_type, "__name__", "") != "PythonLicensing"
        ):
            continue
        bridge = getattr(obj, "licensing_bridge", None)
        bridge_type = type(bridge)
        bridge_type_name = "{0}.{1}".format(
            getattr(bridge_type, "__module__", ""),
            getattr(bridge_type, "__name__", ""),
        )
        bridge_types.add(bridge_type_name)
        owners.append(
            {
                "has_bridge": bridge is not None,
                "bridge_type": bridge_type_name,
                "save_current_set_callable": callable(
                    getattr(bridge, "save_current_set", None)
                ),
            }
        )

    callable_owner_count = sum(
        1 for owner in owners if owner["save_current_set_callable"]
    )
    return {
        "python_version": "{0}.{1}.{2}".format(*sys.version_info[:3]),
        "licensing_module_loaded": "abl.live.licensing" in sys.modules,
        "owner_count": len(owners),
        "callable_save_owner_count": callable_owner_count,
        "bridge_types": sorted(bridge_types),
        "owners": owners,
        "single_callable_owner": len(owners) == 1 and callable_owner_count == 1,
        "mutation_performed": False,
    }


def diagnose_licensing_save_owner(song, ctrl=None):
    """Find Live's existing PythonLicensing owner; never invoke Save."""
    result = _describe_licensing_objects()
    if ctrl:
        ctrl.log_message(
            "Licensing Save owner diagnostic: {0} owner(s), {1} callable".format(
                result["owner_count"], result["callable_save_owner_count"]
            )
        )
    return result

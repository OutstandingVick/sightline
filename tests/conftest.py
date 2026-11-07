import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FakeCtx:
    def __init__(self):
        self.tools, self.hooks = {}, {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, hook_name, callback, **kwargs):
        self.hooks.setdefault(hook_name, []).append(callback)


@pytest.fixture(scope="session")
def plugin():
    spec = importlib.util.spec_from_file_location(
        "sightline_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ctx():
    return FakeCtx()

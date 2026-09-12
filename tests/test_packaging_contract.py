"""The static half of "install your own thing in an empty room and try to use it".

Every assertion here is a fact about the DECLARED install -- what a stranger
gets when they follow the registry entry -- rather than about the source tree
sitting on this machine. Each one is a failure that actually shipped:

  * 0.1.0 was dead on arrival from Jul 28 2026 to Sep 11 2026 because the SDK
    dependency had no upper bound and mcp 2.0.0 deleted the module it imported.
  * 0.1.1 fixed that inside an OPTIONAL extra, while the registry declared the
    bare identifier -- so nobody following the listing installed the SDK at all
    and the server still died on import.
  * `uvx almanac-compute`, which is what an MCP client does with a pypi registry
    entry, failed with "An executable named `almanac-compute` is not provided by
    package `almanac-compute`".
  * `almanac.__version__` said "0.1.0" through two releases because the version
    was written down in two places.

These are cheap and they run everywhere. They do NOT replace the cold probe
(iris-the-maker/earning/mcp_cold_probe.py) -- a passing suite in the room where
the code lives is exactly what hid the first failure for forty-five days.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - the floor is 3.10, which has no tomllib
    tomllib = pytest.importorskip("tomli", reason="need tomllib or tomli to read pyproject")


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


@pytest.fixture(scope="module")
def server_json() -> dict:
    return json.loads(SERVER_JSON.read_text())


def test_mcp_sdk_is_a_hard_dependency(pyproject):
    """The registry declares the bare package name, so the SDK cannot hide in an extra."""
    deps = pyproject["project"]["dependencies"]
    assert any(d.split()[0].startswith("mcp") for d in deps), (
        "the MCP SDK must be a hard dependency: the registry entry declares "
        f"the bare identifier, and a client installing it gets exactly {deps}"
    )


def test_mcp_sdk_has_an_upper_bound(pyproject):
    """2.0.0 deleted mcp.server.fastmcp. An unbounded major is a scheduled outage."""
    spec = next(d for d in pyproject["project"]["dependencies"] if d.startswith("mcp"))
    assert "<" in spec, (
        f"{spec!r} has no upper bound; mcp 2.0.0 already broke this package once "
        "by deleting a module, and the shim knows about 1.x and 2.x only"
    )


def test_a_console_script_is_named_after_the_package(pyproject):
    """`uvx <package>` looks for a console script matching the package name."""
    name = pyproject["project"]["name"]
    scripts = pyproject["project"]["scripts"]
    assert name in scripts, (
        f"`uvx {name}` needs an entry point called {name!r}; "
        f"only {sorted(scripts)} are declared"
    )


def test_every_console_script_points_at_a_real_callable(pyproject):
    import importlib

    for script, target in pyproject["project"]["scripts"].items():
        module_name, _, attr = target.partition(":")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attr)), f"{script} -> {target} is not callable"


def test_python_floor_is_at_least_the_sdks(pyproject):
    """Declaring >=3.9 while depending on a >=3.10 package is a resolver failure."""
    floor = pyproject["project"]["requires-python"].split("#")[0].strip()
    major, minor = (int(x) for x in re.match(r">=\s*(\d+)\.(\d+)", floor).groups())
    assert (major, minor) >= (3, 10), f"{floor} is below the MCP SDK's floor of 3.10"


def test_the_version_is_written_down_exactly_once(pyproject):
    """__init__ said 0.1.0 through two releases; a second copy is a second lie."""
    source = (ROOT / "almanac" / "__init__.py").read_text()
    literal = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.M)
    assert literal is None, (
        f"almanac/__init__.py hard-codes __version__ = {literal.group(1)!r}; "
        "read it from installed metadata instead so pyproject.toml is the only source"
    )


def test_server_json_agrees_with_pyproject(pyproject, server_json):
    """The registry publishes server.json verbatim. Drift here ships a wrong listing."""
    version = pyproject["project"]["version"]
    assert server_json["version"] == version
    package = server_json["packages"][0]
    assert package["identifier"] == pyproject["project"]["name"]
    assert package["version"] == version, (
        f"server.json points the registry at {package['identifier']}=="
        f"{package['version']} while this tree builds {version}"
    )

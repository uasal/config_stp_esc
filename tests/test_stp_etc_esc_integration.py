"""
Integration test: run stp_etc_esc's test suite against the config_stp_esc in this checkout.

This test clones uasal/stp_etc_esc, installs its dependencies (excluding
config_stp_esc so the local checkout remains active), and then runs the
stp_etc_esc tests that exercise config_stp_esc.

A failure here means the current config changes break a **downstream consumer**
(stp_etc_esc), not that the config files themselves are malformed.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
STP_ETC_ESC_REPO = "https://github.com/uasal/stp_etc_esc.git"
STP_ETC_ESC_BRANCH = "develop"

# stp_etc_esc tests that are relevant to config_stp_esc compatibility.
DOWNSTREAM_TEST_FILES = [
    "tests/test_config_stp_esc.py",
    "tests/test_esc_etc_initialization.py",
]


def _run(cmd, cwd=None, env=None, check=True):
    """Run *cmd* and return the CompletedProcess; print output on failure."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if check and result.returncode != 0:
        pytest.fail(
            f"Command failed (exit {result.returncode}):\n"
            f"  {' '.join(str(c) for c in cmd)}\n\n"
            f"--- output ---\n{result.stdout}"
        )
    return result


def _filter_requirements(src_path: Path, dst_path: Path, exclude_pattern: str) -> None:
    """Copy *src_path* to *dst_path*, dropping lines that match *exclude_pattern*."""
    lines = src_path.read_text().splitlines(keepends=True)
    filtered = [ln for ln in lines if not re.search(exclude_pattern, ln, re.IGNORECASE)]
    dst_path.write_text("".join(filtered))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stp_etc_esc_env():
    """
    Set up a temporary directory with a clone of stp_etc_esc and return a
    dict with ``clone_dir`` (Path) and ``env`` (os.environ copy suitable for
    running pytest inside the clone).

    The fixture installs packages in the *same* Python environment that is
    running this test so that no virtual-env creation is needed in CI.
    """
    with tempfile.TemporaryDirectory(prefix="stp_etc_esc_") as tmpdir:
        clone_dir = Path(tmpdir) / "stp_etc_esc"

        # 1. Clone stp_etc_esc -----------------------------------------------
        _run(
            ["git", "clone", "--depth", "1", "--branch", STP_ETC_ESC_BRANCH,
             STP_ETC_ESC_REPO, str(clone_dir)],
        )

        pip = [sys.executable, "-m", "pip", "install", "--quiet"]

        # 2. Install local config_stp_esc FIRST so it takes priority ----------
        _run(pip + ["--no-deps", str(REPO_ROOT)])

        # 3. Install stp_etc_esc deps, skipping config_stp_esc ---------------
        orig_req = clone_dir / "requirements.txt"
        filtered_req = clone_dir / "requirements_filtered.txt"
        # Drop lines that reference config_stp_esc (git URL or bare name).
        _filter_requirements(orig_req, filtered_req, r"config_stp_esc")
        _run(pip + ["-r", str(filtered_req)])

        # 4. Install stp_etc_esc itself (no deps to avoid overwriting config) -
        _run(pip + ["--no-deps", str(clone_dir)])

        # 5. Build an env with MPLBACKEND=Agg for headless CI -----------------
        env = os.environ.copy()
        env["MPLBACKEND"] = "Agg"

        yield {"clone_dir": clone_dir, "env": env}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_downstream_config_stp_esc(stp_etc_esc_env):
    """
    Run stp_etc_esc's test_config_stp_esc.py against the local config_stp_esc checkout.

    A failure here means the current config changes break stp_etc_esc's
    config-loading tests, NOT that config_stp_esc itself is malformed.
    """
    clone_dir = stp_etc_esc_env["clone_dir"]
    env = stp_etc_esc_env["env"]

    test_file = clone_dir / "tests" / "test_config_stp_esc.py"
    result = _run(
        [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
        cwd=str(clone_dir),
        env=env,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail(
            "DOWNSTREAM COMPATIBILITY FAILURE — stp_etc_esc/tests/test_config_stp_esc.py "
            "failed against this config_stp_esc branch.\n\n"
            "This is a downstream integration failure, not a config validation failure.\n\n"
            f"--- pytest output ---\n{result.stdout}"
        )


@pytest.mark.integration
def test_downstream_esc_etc_initialization(stp_etc_esc_env):
    """
    Run stp_etc_esc's test_esc_etc_initialization.py (specifically
    test_configs_instrument) against the local config_stp_esc checkout.

    A failure here means the current config changes break stp_etc_esc's
    ETC initialization, NOT that config_stp_esc itself is malformed.
    """
    clone_dir = stp_etc_esc_env["clone_dir"]
    env = stp_etc_esc_env["env"]

    test_file = clone_dir / "tests" / "test_esc_etc_initialization.py"
    result = _run(
        [
            sys.executable, "-m", "pytest",
            str(test_file), "-v", "--tb=short",
            "-k", "test_configs_instrument",
        ],
        cwd=str(clone_dir),
        env=env,
        check=False,
    )

    if result.returncode != 0:
        pytest.fail(
            "DOWNSTREAM COMPATIBILITY FAILURE — stp_etc_esc/tests/test_esc_etc_initialization.py "
            "::test_configs_instrument failed against this config_stp_esc branch.\n\n"
            "This is a downstream integration failure, not a config validation failure.\n\n"
            f"--- pytest output ---\n{result.stdout}"
        )

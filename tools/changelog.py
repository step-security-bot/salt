"""
These commands are used manage Salt's changelog.
"""
# pylint: disable=resource-leakage,broad-except
from __future__ import annotations

import datetime
import logging
import os
import pathlib
import subprocess
import sys
import textwrap

from ptscripts import Context, command_group

log = logging.getLogger(__name__)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Define the command group
changelog = command_group(
    name="changelog",
    help="Changelog tools",
    description=__doc__,
    venv_config={
        "requirements_files": [
            REPO_ROOT
            / "requirements"
            / "static"
            / "ci"
            / "py{}.{}".format(*sys.version_info)
            / "changelog.txt"
        ],
    },
)


def _get_changelog_contents(ctx: Context, version: str):
    """
    Return the full changelog generated by towncrier.
    """
    return ctx.run(
        "towncrier",
        "build",
        "--draft",
        f"--version={version}",
        capture=True,
    ).stdout.decode()


def _get_pkg_changelog_contents(ctx: Context, version: str):
    """
    Return a version of the changelog entries suitable for packaged changelogs.
    """
    changes = _get_changelog_contents(ctx, version)
    changes = "\n".join(changes.split("\n")[2:])
    changes = changes.replace(
        textwrap.dedent(
            """
        Removed
        -------

        """
        ),
        "",
    )
    changes = changes.replace(
        textwrap.dedent(
            """
        Deprecated
        ----------

        """
        ),
        "",
    )
    changes = changes.replace(
        textwrap.dedent(
            """
        Changed
        -------

        """
        ),
        "",
    )
    changes = changes.replace(
        textwrap.dedent(
            """
        Fixed
        -----

        """
        ),
        "",
    )
    changes = changes.replace(
        textwrap.dedent(
            """
        Added
        -----

        """
        ),
        "",
    )
    return changes


def _get_salt_version():
    return (
        subprocess.run(
            ["python3", "salt/version.py"], stdout=subprocess.PIPE, check=True
        )
        .stdout.decode()
        .strip()
    )


@changelog.command(
    name="update-rpm",
    arguments={
        "salt_version": {
            "help": (
                "The salt package version. If not passed "
                "it will be discovered by running 'python3 salt/version.py'."
            ),
            "nargs": "?",
            "default": None,
        },
        "draft": {
            "help": "Do not make any changes, instead output what would be changed.",
        },
    },
)
def update_rpm(ctx: Context, salt_version: str, draft: bool = False):
    if salt_version is None:
        salt_version = _get_salt_version()
    changes = _get_pkg_changelog_contents(ctx, salt_version)
    ctx.info("Salt version is %s", salt_version)
    orig = ctx.run(
        "sed",
        f"s/Version: .*/Version: {salt_version}/g",
        "pkg/rpm/salt.spec",
        capture=True,
        check=True,
    ).stdout.decode()
    dt = datetime.datetime.utcnow()
    date = dt.strftime("%a %b %d %Y")
    header = f"* {date} Salt Project Packaging <saltproject-packaging@vmware.com> - {salt_version}\n"
    parts = orig.split("%changelog")
    tmpspec = "pkg/rpm/salt.spec.1"
    with open(tmpspec, "w") as wfp:
        wfp.write(parts[0])
        wfp.write("%changelog\n")
        wfp.write(header)
        wfp.write(changes)
        wfp.write(parts[1])
    try:
        with open(tmpspec) as rfp:
            if draft:
                ctx.info(rfp.read())
            else:
                with open("pkg/rpm/salt.spec", "w") as wfp:
                    wfp.write(rfp.read())
    finally:
        os.remove(tmpspec)


@changelog.command(
    name="update-deb",
    arguments={
        "salt_version": {
            "help": (
                "The salt package version. If not passed "
                "it will be discovered by running 'python3 salt/version.py'."
            ),
            "nargs": "?",
            "default": None,
        },
        "draft": {
            "help": "Do not make any changes, instead output what would be changed.",
        },
    },
)
def update_deb(ctx: Context, salt_version: str, draft: bool = False):
    if salt_version is None:
        salt_version = _get_salt_version()
    changes = _get_pkg_changelog_contents(ctx, salt_version)
    formated = "\n".join([f"  {_.replace('-', '*', 1)}" for _ in changes.split("\n")])
    dt = datetime.datetime.utcnow()
    date = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    tmpchanges = "pkg/rpm/salt.spec.1"
    with open(tmpchanges, "w") as wfp:
        wfp.write(f"salt ({salt_version}) stable; urgency=medium\n\n")
        wfp.write(formated)
        wfp.write(
            f"\n -- Salt Project Packaging <saltproject-packaging@vmware.com> {date}\n\n"
        )
        with open("pkg/debian/changelog") as rfp:
            wfp.write(rfp.read())
    try:
        with open(tmpchanges) as rfp:
            if draft:
                ctx.info(rfp.read())
            else:
                with open("pkg/debian/changelog", "w") as wfp:
                    wfp.write(rfp.read())
    finally:
        os.remove(tmpchanges)


@changelog.command(
    name="update-release-notes",
    arguments={
        "salt_version": {
            "help": (
                "The salt version used to generate the release notes. If not passed "
                "it will be discovered by running 'python3 salt/version.py'."
            ),
            "nargs": "?",
            "default": None,
        },
        "draft": {
            "help": "Do not make any changes, instead output what would be changed.",
        },
    },
)
def update_release_notes(ctx: Context, salt_version: str, draft: bool = False):
    if salt_version is None:
        salt_version = _get_salt_version()
    if "+" in salt_version:
        major_version = salt_version.split("+", 1)[0]
    else:
        major_version = salt_version
    changes = _get_changelog_contents(ctx, salt_version)
    changes = "\n".join(changes.split("\n")[2:])
    tmpnotes = f"doc/topics/releases/{salt_version}.rst.tmp"
    try:
        with open(f"doc/topics/releases/{major_version}.rst") as rfp:
            existing = rfp.read()
    except FileNotFoundError:
        existing = ""
    with open(tmpnotes, "w") as wfp:
        wfp.write(existing)
        wfp.write(changes)
    try:
        with open(tmpnotes) as rfp:
            contents = rfp.read().strip()
            if draft:
                ctx.print(contents, soft_wrap=True)
            else:
                with open(f"doc/topics/releases/{salt_version}.rst", "w") as wfp:
                    wfp.write(contents)
    finally:
        os.remove(tmpnotes)


@changelog.command(
    name="update-changelog-md",
    arguments={
        "salt_version": {
            "help": (
                "The salt version to use in the changelog. If not passed "
                "it will be discovered by running 'python3 salt/version.py'."
            ),
            "nargs": "?",
            "default": None,
        },
        "draft": {
            "help": "Do not make any changes, instead output what would be changed.",
        },
    },
)
def generate_changelog_md(ctx: Context, salt_version: str, draft: bool = False):
    if salt_version is None:
        salt_version = _get_salt_version()
    cmd = ["towncrier", "build", f"--version={salt_version}"]
    if draft:
        cmd += ["--draft"]
    else:
        cmd += ["--yes"]
    ctx.run(*cmd, check=True)
    ctx.run("git", "restore", "--staged", "CHANGELOG.md", "changelog/", check=True)

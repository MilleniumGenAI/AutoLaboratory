"""One module per CLI subcommand. cli.py only builds the parser and prints JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import (
    baseline,
    cancel,
    dashboard,
    doctor,
    guide,
    promote,
    preflight,
    recover,
    resume,
    status,
    storage,
    trial,
    vault,
)

COMMANDS = (
    doctor, baseline, status, recover, trial, vault, cancel,
    dashboard, promote, guide, preflight, resume, storage,
)


def register_all(subparsers: Any) -> None:
    for command in COMMANDS:
        command.register(subparsers)


def run_command(args: Any, labs_root: Path | None) -> dict[str, Any]:
    by_name = {
        "baseline": baseline, "status": status,
        "recover": recover, "trial": trial,
        "vault": vault, "dashboard": dashboard, "doctor": doctor, "promote": promote,
        "storage": storage, "cancel": cancel,
        "guide": guide, "preflight": preflight, "resume": resume,
    }
    return by_name[args.command].run(args, labs_root)

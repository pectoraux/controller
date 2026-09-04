"""Command-line entry point: ``python -m controller validate``.

Local, offline smoke test. Validates repository authority (fail-closed on
any contradiction) and prints the reconstructed controller state. Exit
code 0 means authority is consistent and reconstructable; exit code 1
means the controller refuses to proceed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from controller import __version__, reconstruct
from controller.authority import verify_authority
from controller.errors import ControllerError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="controller",
        description="Pectoraux Controller (CTRL-001 foundation). "
        "Offline repository-authority validation and state reconstruction.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate",
        help="Validate repository authority and print reconstructed state.",
    )
    validate.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Controller repository root (default: current directory).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    args = _build_parser().parse_args(argv)

    if args.command == "validate":
        repo_root: Path = args.repo
        try:
            program = verify_authority(repo_root)
            state = reconstruct(repo_root)
        except ControllerError as exc:
            print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
            return 1
        print("controller authority: OK")
        print(f"repository: {program.repository}")
        print(f"schema version: {program.schema_version}")
        print(f"active work item: {program.active_work_item}")
        print(f"lifecycle state: {state.lifecycle.value}")
        print(f"automation stage: {program.automation_stage}")
        print(f"completed items: {len(program.completed)}")
        return 0

    # Unreachable: argparse enforces the subcommand choice.
    raise AssertionError(f"unhandled command: {args.command}")  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())

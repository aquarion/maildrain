#!/usr/bin/env python3
"""
Quick test runner script for maildrain.

This script provides a simple way to run the test suite and check coverage.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command: list[str], description: str) -> bool:
    """Run a command and return whether it succeeded."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(command)}")
    print(f"{'=' * 60}")

    result = subprocess.run(command, capture_output=False)
    success = result.returncode == 0

    if success:
        print(f"✅ {description} completed successfully")
    else:
        print(f"❌ {description} failed with exit code {result.returncode}")

    return success


def main() -> int:
    """Run the test suite with different configurations."""
    # Ensure we're in the right directory
    project_root = Path(__file__).parent.parent
    print(f"Running tests from: {project_root}")

    # List of test commands to run
    test_commands = [
        (["poetry", "run", "pytest", "--version"], "Checking pytest installation"),
        (["poetry", "run", "pytest", "tests/", "-v"], "Running all tests (verbose)"),
        (
            [
                "poetry",
                "run",
                "pytest",
                "tests/",
                "--cov=maildrain",
                "--cov-report=term",
            ],
            "Running tests with coverage",
        ),
    ]

    all_passed = True

    for command, description in test_commands:
        success = run_command(command, description)
        if not success:
            all_passed = False

    print(f"\n{'=' * 60}")
    if all_passed:
        print("🎉 All tests completed successfully!")
        print("\nTo run tests manually:")
        print("  poetry run pytest                    # Run all tests")
        print("  poetry run pytest -v                 # Verbose output")
        print("  poetry run pytest --cov=maildrain    # With coverage")
        print("  poetry run pytest tests/test_gmail_client.py  # Specific file")
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

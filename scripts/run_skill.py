"""
run_skill.py — Load and print a SKILL.md definition.

Usage:
    python scripts/run_skill.py memory-notes
    python scripts/run_skill.py --list
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def list_skills() -> list[str]:
    return sorted([p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")])


def load_skill(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {path}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a SKILL.md definition.")
    parser.add_argument("skill", nargs="?", help="Skill name to load.")
    parser.add_argument("--list", action="store_true", help="List all available skills.")
    args = parser.parse_args()

    if args.list:
        skills = list_skills()
        print("Available skills:")
        for s in skills:
            print(f"  - {s}")
        return

    if not args.skill:
        parser.print_help()
        sys.exit(1)

    try:
        content = load_skill(args.skill)
        print(content)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

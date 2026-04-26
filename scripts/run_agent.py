"""
run_agent.py — CLI entrypoint for running an agent interactively.

Usage:
    python scripts/run_agent.py --agent primary-assistant
    python scripts/run_agent.py --agent architecture-advisor

Requires: anthropic (pip install anthropic)
Set ANTHROPIC_API_KEY in your environment.
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_agent_prompt(agent_name: str) -> str:
    """Load AGENT.md for the given agent."""
    agent_path = REPO_ROOT / "agents" / agent_name / "AGENT.md"
    if not agent_path.exists():
        raise FileNotFoundError(f"Agent not found: {agent_path}")
    return agent_path.read_text(encoding="utf-8")


def load_agents_root() -> str:
    """Load root AGENTS.md."""
    return (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")


def run_interactive(agent_name: str, model: str = "claude-sonnet-4-5") -> None:
    """
    Run a simple interactive chat loop with the specified agent.
    Uses the Anthropic Messages API.
    """
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    root_instructions = load_agents_root()
    agent_instructions = load_agent_prompt(agent_name)
    system_prompt = f"{root_instructions}\n\n---\n\n{agent_instructions}"

    print(f"\n[agent-workspace] Running agent: {agent_name}")
    print(f"[agent-workspace] Model: {model}")
    print("Type 'exit' or 'quit' to stop.\n")

    messages = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if user_input.lower() in ("exit", "quit"):
            print("Bye.")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )

        assistant_text = response.content[0].text
        print(f"\nAssistant: {assistant_text}\n")

        messages.append({"role": "assistant", "content": assistant_text})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an agent from the workspace.")
    parser.add_argument(
        "--agent",
        default="primary-assistant",
        choices=["primary-assistant", "architecture-advisor"],
        help="Agent to run.",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Model to use (default: claude-sonnet-4-5).",
    )
    args = parser.parse_args()
    run_interactive(agent_name=args.agent, model=args.model)


if __name__ == "__main__":
    main()

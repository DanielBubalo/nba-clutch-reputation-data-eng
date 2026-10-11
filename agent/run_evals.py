"""Run the analyst agent on every eval case and score the answers.

Usage (from the project root):
    python3 agent/run_evals.py                 # every case
    python3 agent/run_evals.py tier_counts     # only the cases you name
"""

import json
import re
import sys

import anthropic
from rich.console import Console
from rich.markup import escape
from rich.table import Table

import analyst
from eval_cases import CASES

console = Console()

JUDGE_PROMPT = """You grade answers from an AI data analyst.
You get a question, the analyst's answer, and a description of what a correct answer does.
Decide whether the answer does what the description says. Judge only against the description.
Reply with JSON only, no other text: {"pass": true or false, "reason": "one short sentence"}"""


# ------------------------------------------------------------ the checks


def numbers_in(text: str) -> list[float]:
    """Every number written in the answer: 4,031, -0.0153, −.334, 1.5 all count."""
    text = text.replace("\u2212", "-").replace(",", "")
    return [float(match) for match in re.findall(r"-?\d*\.?\d+", text)]


def has_number(
    found: list[float], expected: float, tolerance: float, percent_ok: bool
) -> bool:
    candidates = [expected, expected * 100] if percent_ok else [expected]
    scale = [tolerance, tolerance * 100] if percent_ok else [tolerance]
    return any(
        abs(number - target) <= tol + 1e-9
        for number in found
        for target, tol in zip(candidates, scale)
    )


def truth_rows(case: dict) -> list[dict]:
    with analyst.connect() as con:
        df = con.execute(case["truth_sql"]).df()
    return df.to_dict("records")


def judge(
    client: anthropic.Anthropic, question: str, answer: str, rubric: str
) -> tuple[bool, str]:
    response = client.messages.create(
        model=analyst.MODEL,
        max_tokens=300,
        system=JUDGE_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Question:\n{question}\n\nAnswer:\n{answer}\n\nA correct answer:\n{rubric}",
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        verdict = json.loads(text)
        return bool(verdict["pass"]), str(verdict.get("reason", ""))
    except (json.JSONDecodeError, KeyError):
        return False, f"judge reply wasn't valid JSON: {text[:80]}"


def score(
    case: dict, result: analyst.AgentResult, client: anthropic.Anthropic
) -> list[str]:
    """Return every problem with this answer. An empty list means it passed."""
    problems = []
    if not result.complete:
        problems.append(f"answer incomplete (stop reason: {result.stop_reason})")

    if "truth_sql" in case:
        rows = truth_rows(case)
        found = numbers_in(result.answer)
        for column in case.get("numbers", []):
            for row in rows:
                expected = float(row[column])
                if not has_number(
                    found,
                    expected,
                    case.get("tolerance", 0),
                    case.get("percent_ok", False),
                ):
                    problems.append(f"missing {column} = {expected:g}")
        if "names" in case:
            for row in rows:
                name = str(row[case["names"]])
                if name.lower() not in result.answer.lower():
                    problems.append(f"missing name {name}")

    if "judge" in case:
        passed, reason = judge(client, case["question"], result.answer, case["judge"])
        if not passed:
            problems.append(f"judge: {reason}")

    return problems


# ------------------------------------------------------------ the run


def main() -> None:
    wanted = sys.argv[1:]
    cases = [case for case in CASES if not wanted or case["id"] in wanted]
    unknown = set(wanted) - {case["id"] for case in CASES}
    if unknown:
        sys.exit(f"Unknown case id(s): {', '.join(sorted(unknown))}")

    analyst.trace.quiet = (
        True  # hide each run's step-by-step trace; the table sums it up
    )
    client = anthropic.Anthropic()
    table = Table(title="Analyst agent evals", show_lines=True)
    for column in ("Case", "Result", "Steps", "Failed queries", "Time", "Problems"):
        table.add_column(column)

    passed = 0
    for number, case in enumerate(cases, start=1):
        with console.status(f"[dim]{number}/{len(cases)} {case['id']}…[/]"):
            result = analyst.ask(case["question"])
            problems = score(case, result, client)
        ok = not problems
        passed += ok
        console.print(f"{'[green]✓' if ok else '[red]✗'} {case['id']}[/]")
        table.add_row(
            case["id"],
            "[green]PASS[/]" if ok else "[red]FAIL[/]",
            str(result.steps),
            str(result.failed_queries),
            f"{result.seconds:.0f}s",
            escape("\n".join(problems)) or "[dim]-[/]",
        )

    console.print()
    console.print(table)
    colour = "green" if passed == len(cases) else "red"
    console.print(f"\n[bold {colour}]{passed}/{len(cases)} passed[/]")
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()

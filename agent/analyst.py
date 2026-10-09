"""Analyst agent: answers questions about the NBA clutch data using read-only SQL.

Usage (from the project root):
    python3 agent/analyst.py "Which Star player-seasons had the biggest clutch decline?"
"""

import json
import sys
import threading
import time
from pathlib import Path

import anthropic
import duckdb
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nba_clutch.duckdb"
MANIFEST_PATH = ROOT / "dbt" / "target" / "manifest.json"
MAX_ROWS = 50
MAX_STEPS = 10
MAX_TOKENS = 8192
QUERY_TIMEOUT_SECONDS = 30
MODEL = "claude-sonnet-5-5"

console = Console()  # the final answer
trace = Console(stderr=True)  # the agent's working steps
VERBOSE = False  # set by --verbose: print each tool's full output in the trace


# ---------------------------------------------------------------- tools


def connect() -> duckdb.DuckDBPyConnection:
    """Open the database read-only, with no access to files, other databases, or the network."""
    con = duckdb.connect(
        str(DB_PATH), read_only=True, config={"enable_external_access": False}
    )
    con.execute("SET lock_configuration = true")  # the query can't switch it back on
    return con


def check_query(con: duckdb.DuckDBPyConnection, query: str) -> str | None:
    """Return a reason to reject the query, or None if it's a single SELECT."""
    statements = con.extract_statements(query)
    if len(statements) != 1:
        return f"Send exactly one statement per query (got {len(statements)})."
    if statements[0].type != duckdb.StatementType.SELECT:
        return f"Only SELECT queries are allowed (got {statements[0].type.name})."
    return None


def format_column(name: str, dtype: str, column_docs: dict) -> str:
    """Show a column's type, plus its schema.yml description if it has one."""
    doc = column_docs.get(name, {}).get("description", "")
    return f"{name} ({dtype}): {doc}" if doc else f"{name} ({dtype})"


def describe_models() -> str:
    """List the analysis models with their dbt descriptions and columns."""
    if not MANIFEST_PATH.exists():
        return "manifest.json not found. Run `dbt parse --profiles-dir .` from dbt/."
    manifest = json.loads(MANIFEST_PATH.read_text())
    lines = []
    with connect() as con:
        for node in manifest["nodes"].values():
            if node["resource_type"] != "model" or node["path"].startswith("staging/"):
                continue
            columns = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [node["name"]],
            ).fetchall()
            column_text = ", ".join(
                format_column(name, dtype, node["columns"]) for name, dtype in columns
            )
            lines.append(
                f"{node['name']}: {node['description']}\n  columns: {column_text}"
            )
    return "\n\n".join(lines)


def run_sql(query: str) -> str:
    """Run one guarded, read-only query and return the result as text."""
    try:
        with connect() as con:
            rejection = check_query(con, query)
            if rejection:
                return f"Query failed: {rejection}"
            timer = threading.Timer(QUERY_TIMEOUT_SECONDS, con.interrupt)
            timer.start()
            try:
                df = con.execute(query).df()
            finally:
                timer.cancel()
    except duckdb.InterruptException:
        return f"Query failed: timed out after {QUERY_TIMEOUT_SECONDS} seconds. Simplify it or add filters."
    except Exception as error:
        return f"Query failed: {error}"
    if df.empty:
        return "Query returned no rows."
    text = df.head(MAX_ROWS).to_string(index=False)
    if len(df) > MAX_ROWS:
        text += f"\n... ({len(df)} rows total, showing first {MAX_ROWS})"
    return text


# ------------------------------------------------- what Claude is told

TOOLS = [
    {
        "name": "describe_models",
        "description": (
            "List the analysis tables in the NBA clutch database, with each table's "
            "description and its column names and types. Call this first."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_sql",
        "description": (
            "Run one read-only DuckDB SQL query against the analysis tables and get the "
            f"result as text (at most {MAX_ROWS} rows shown). Use SELECT only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A single DuckDB SELECT query.",
                }
            },
            "required": ["query"],
        },
    },
]

SYSTEM_PROMPT = """You are a data analyst for an NBA clutch-performance database.
The project asks whether "Star" players really perform better in the clutch, or whether reputation outpaces results.

Rules:
- Call describe_models first to learn the tables and columns. Do not guess table or column names.
- Use only SELECT queries. The database is read-only.
- Every number in your answer must come from a query result in this conversation.
- If a query fails, read the error, fix the query, and try again.
- If the data cannot answer the question, say so plainly instead of guessing.
- Finish with a short answer, then a "Queries used" section. Put each query in its own ```sql code block, formatted across several lines (SELECT, FROM, WHERE, ORDER BY each on their own line), with a short bold label above it saying what that query was for. Only include queries that shaped the answer."""


def run_tool(name: str, tool_input: dict) -> str:
    if name == "describe_models":
        return describe_models()
    if name == "run_sql":
        return run_sql(tool_input["query"])
    return f"Unknown tool: {name}"


# ------------------------------------------------------------ display


def show_tool_call(step: int, name: str, tool_input: dict, output: str) -> None:
    """Print one tool call: what was asked, and a one-line summary of what came back."""
    trace.print(f"\n[bold cyan]Step {step}[/] [cyan]{name}[/]")
    if name == "run_sql":
        trace.print(
            Syntax(
                tool_input.get("query", ""),
                "sql",
                theme="monokai",
                word_wrap=True,
                padding=(0, 2),
            )
        )

    if output.startswith("Query failed"):
        trace.print(f"  [bold red]✗ {escape(output.splitlines()[0])}[/]")
    elif output == "Query returned no rows.":
        trace.print("  [yellow]○ no rows[/]")
    elif name == "describe_models":
        trace.print(
            f"  [green]✓[/] [dim]{output.count(chr(10) + chr(10)) + 1} tables described[/]"
        )
    else:
        lines = output.splitlines()
        if lines[-1].startswith("..."):
            summary = lines[-1].strip(". ")
        else:
            summary = f"{len(lines) - 1} rows"
        trace.print(f"  [green]✓[/] [dim]{summary}[/]")

    if VERBOSE:
        trace.print(Panel(escape(output), border_style="dim", padding=(0, 1)))


# ------------------------------------------------------------- the loop

# How each way of finishing is reported: (complete?, colour, message shown to you)
STOP_REASONS = {
    "end_turn": (True, "green", "✓ Complete: the agent finished its answer"),
    "max_tokens": (
        False,
        "yellow",
        f"⚠ Truncated: the answer hit the {MAX_TOKENS:,}-token output limit",
    ),
    "refusal": (False, "red", "✗ Stopped: the model declined to answer"),
}


def ask(question: str, max_steps: int = MAX_STEPS) -> tuple[str, bool]:
    """Run the agent. Returns (answer text, whether the answer is complete)."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": question}]
    started = time.perf_counter()

    for step in range(1, max_steps + 1):
        with trace.status("[dim]Thinking…[/]", spinner="dots"):
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        messages.append({"role": "assistant", "content": response.content})
        text = "".join(block.text for block in response.content if block.type == "text")

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                output = run_tool(block.name, block.input)
                show_tool_call(step, block.name, block.input, output)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": output}
                )
            messages.append({"role": "user", "content": results})
            continue

        complete, colour, message = STOP_REASONS.get(
            response.stop_reason,
            (False, "red", "✗ Stopped: unexpected stop reason"),
        )
        report_stop(colour, message, response.stop_reason, step, started)
        return text, complete

    report_stop(
        "red",
        f"✗ Stopped: reached the {max_steps}-step limit before finishing",
        "max_steps",
        max_steps,
        started,
    )
    return (
        "The agent ran out of steps before reaching an answer. Try a narrower question.",
        False,
    )


def report_stop(
    colour: str, message: str, reason: str, steps: int, started: float
) -> None:
    """Print why the agent stopped, in the trace footer."""
    elapsed = time.perf_counter() - started
    trace.print(f"\n[bold {colour}]{message}[/] [dim](stop reason: {reason})[/]")
    trace.print(f"[dim]{steps} steps · {elapsed:.1f}s[/]")


if __name__ == "__main__":
    VERBOSE = "--verbose" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--verbose"]
    if len(args) != 1:
        sys.exit('Usage: python3 agent/analyst.py [--verbose] "your question"')
    question = args[0]
    console.print(
        Panel(
            escape(question), title="[bold]NBA Clutch Analyst[/]", border_style="cyan"
        )
    )
    answer, complete = ask(question)
    console.print(
        Panel(
            Markdown(answer, code_theme="monokai"),
            title=(
                "[bold]Answer[/]" if complete else "[bold yellow]Answer (incomplete)[/]"
            ),
            border_style="green" if complete else "yellow",
            padding=(1, 2),
        )
    )
    sys.exit(0 if complete else 1)

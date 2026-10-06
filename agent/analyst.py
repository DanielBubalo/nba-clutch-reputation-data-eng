"""Analyst agent: answers questions about the NBA clutch data using read-only SQL.

Usage (from the project root):
    python3 agent/analyst.py "Which Star player-seasons had the biggest clutch decline?"
"""

import json
import sys
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
MODEL = "claude-sonnet-5-5"

console = Console()  # the final answer
trace = Console(stderr=True)  # the agent's working steps


# ---------------------------------------------------------------- tools


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
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
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
    """Run one read-only query and return the result as text."""
    try:
        with duckdb.connect(str(DB_PATH), read_only=True) as con:
            df = con.execute(query).df()
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


# ------------------------------------------------------------- the loop


def ask(question: str, max_steps: int = 10) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": question}]
    started = time.perf_counter()

    for step in range(1, max_steps + 1):
        with trace.status("[dim]Thinking…[/]", spinner="dots"):
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            elapsed = time.perf_counter() - started
            trace.print(f"\n[dim]{step} steps · {elapsed:.1f}s[/]")
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

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

    return f"Stopped after {max_steps} steps without a final answer."


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Usage: python3 agent/analyst.py "your question"')
    question = sys.argv[1]
    console.print(
        Panel(
            escape(question), title="[bold]NBA Clutch Analyst[/]", border_style="cyan"
        )
    )
    answer = ask(question)
    console.print(
        Panel(
            Markdown(answer, code_theme="monokai"),
            title="[bold]Answer[/]",
            border_style="green",
            padding=(1, 2),
        )
    )

"""Analyst agent: answers questions about the NBA clutch data using read-only SQL.

Usage (from the project root):
    python3 agent/analyst.py "Which Star player-seasons had the biggest clutch decline?"
"""

import json
import sys
from pathlib import Path

import anthropic
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "nba_clutch.duckdb"
MANIFEST_PATH = ROOT / "dbt" / "target" / "manifest.json"
MAX_ROWS = 50
MODEL = "claude-sonnet-5-5"


# ---------------------------------------------------------------- tools


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
            column_text = ", ".join(f"{name} ({dtype})" for name, dtype in columns)
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
- Finish with a short answer, then list the queries you used to get it."""


def run_tool(name: str, tool_input: dict) -> str:
    if name == "describe_models":
        return describe_models()
    if name == "run_sql":
        return run_sql(tool_input["query"])
    return f"Unknown tool: {name}"


# ------------------------------------------------------------- the loop


def ask(question: str, max_steps: int = 10) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": question}]

    for step in range(1, max_steps + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"\n[step {step}] {block.name}", file=sys.stderr)
            if block.name == "run_sql":
                print(block.input.get("query", ""), file=sys.stderr)
            output = run_tool(block.name, block.input)
            if output.startswith("Query failed"):
                print(f" -> {output}", file=sys.stderr)
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": output}
            )
        messages.append({"role": "user", "content": results})

    return f"Stopped after {max_steps} steps without a final answer."


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Usage: python3 agent/analyst.py "your question"')
    print("\n" + ask(sys.argv[1]))

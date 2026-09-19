"""SQLite-backed MCP server for auditable recruitment-round history."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


class RoundStore:
    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS screening_rounds (
                id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL,
                round_number INTEGER NOT NULL, candidate_name TEXT,
                score REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def record(self, thread_id: str, round_number: int,
               candidate_name: str | None, score: float | None) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO screening_rounds "
                "(thread_id, round_number, candidate_name, score) VALUES (?, ?, ?, ?)",
                (thread_id, round_number, candidate_name, score),
            )
        return {"id": cursor.lastrowid, "thread_id": thread_id,
                "round_number": round_number, "candidate_name": candidate_name,
                "score": score}

    def list(self, thread_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM screening_rounds"
        params: tuple[Any, ...] = ()
        if thread_id:
            query += " WHERE thread_id = ?"
            params = (thread_id,)
        query += " ORDER BY id"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params)]


def create_server(database: str | Path) -> MCPServer:
    store = RoundStore(database)
    server = MCPServer(name="recruitment-mcp-server", version="0.1.0")

    @server.tool(name="record_round", structured_output=True)
    def record_round(thread_id: str, round_number: int,
                     candidate_name: str | None = None,
                     score: float | None = None) -> dict[str, Any]:
        """Persist one agent screening-round result."""
        return _success(store.record(thread_id, round_number, candidate_name, score))

    @server.tool(name="list_rounds", structured_output=True)
    def list_rounds(thread_id: str | None = None) -> dict[str, Any]:
        """List persisted screening rounds, optionally by thread."""
        return _success({"rounds": store.list(thread_id)})

    @server.resource("recruitment://rounds", name="round_history",
                     mime_type="application/json")
    def round_history() -> str:
        """Return all recorded screening rounds."""
        return json.dumps(_success({"rounds": store.list()}))

    return server


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = create_server(os.getenv("MCP_RECRUITMENT_DB", "runtime/recruitment.db"))
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

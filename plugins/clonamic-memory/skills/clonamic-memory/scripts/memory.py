#!/usr/bin/env python3
"""Explicit local memory operations."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    tags TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    source TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    PRIMARY KEY (source, target, relation)
);
CREATE INDEX IF NOT EXISTS edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS edges_target ON edges(target);
"""


def store(path: str | Path, memory_id: str, content: str, tags: Iterable[str]) -> dict[str, Any]:
    resolved_id = _required(memory_id, "id")
    resolved_content = _required(content, "content")
    resolved_tags = _tags(tags)
    now = _now()
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO memories (id, content, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                tags = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (resolved_id, resolved_content, json.dumps(resolved_tags, ensure_ascii=False), now, now),
        )
        row = connection.execute("SELECT * FROM memories WHERE id = ?", (resolved_id,)).fetchone()
    return _memory(row)


def recall(path: str | Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    terms = set(_tokens(_required(query, "query")))
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    with _connect(path) as connection:
        rows = connection.execute("SELECT * FROM memories").fetchall()
    scored: list[tuple[int, str, sqlite3.Row]] = []
    folded_query = query.casefold()
    for row in rows:
        tags = json.loads(row["tags"])
        haystack = f"{row['content']} {' '.join(tags)}".casefold()
        overlap = len(terms.intersection(_tokens(haystack)))
        score = overlap * 10 + (5 if folded_query in haystack else 0)
        if score:
            scored.append((score, row["updated_at"], row))
    scored.sort(key=lambda entry: (-entry[0], entry[1], entry[2]["id"]))
    output = []
    for score, _, row in scored[:limit]:
        item = _memory(row)
        item["score"] = score
        output.append(item)
    return output


def forget(path: str | Path, memory_id: str) -> bool:
    resolved_id = _required(memory_id, "id")
    with _connect(path) as connection:
        cursor = connection.execute("DELETE FROM memories WHERE id = ?", (resolved_id,))
    return cursor.rowcount == 1


def link(path: str | Path, source: str, target: str, relation: str) -> dict[str, str]:
    resolved_source = _required(source, "source")
    resolved_target = _required(target, "target")
    resolved_relation = _required(relation, "relation")
    if resolved_source == resolved_target:
        raise ValueError("self edges are not allowed")
    with _connect(path) as connection:
        existing = {
            row["id"]
            for row in connection.execute(
                "SELECT id FROM memories WHERE id IN (?, ?)",
                (resolved_source, resolved_target),
            )
        }
        missing = {resolved_source, resolved_target} - existing
        if missing:
            raise KeyError(",".join(sorted(missing)))
        connection.execute(
            "INSERT OR REPLACE INTO edges (source, target, relation) VALUES (?, ?, ?)",
            (resolved_source, resolved_target, resolved_relation),
        )
    return {"source": resolved_source, "target": resolved_target, "relation": resolved_relation}


def graph(path: str | Path, anchor: str, *, depth: int = 2, limit: int = 20) -> dict[str, Any]:
    resolved_anchor = _required(anchor, "anchor")
    if depth < 0 or depth > 4:
        raise ValueError("depth must be between 0 and 4")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    with _connect(path) as connection:
        if connection.execute("SELECT 1 FROM memories WHERE id = ?", (resolved_anchor,)).fetchone() is None:
            raise KeyError(resolved_anchor)
        visited = {resolved_anchor}
        order = [resolved_anchor]
        pending = deque([(resolved_anchor, 0)])
        while pending and len(order) < limit:
            current, current_depth = pending.popleft()
            if current_depth >= depth:
                continue
            rows = connection.execute(
                """
                SELECT source, target FROM edges
                WHERE source = ? OR target = ?
                ORDER BY source, target, relation
                """,
                (current, current),
            ).fetchall()
            for row in rows:
                neighbor = row["target"] if row["source"] == current else row["source"]
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                order.append(neighbor)
                pending.append((neighbor, current_depth + 1))
                if len(order) >= limit:
                    break
        placeholders = ",".join("?" for _ in order)
        nodes = connection.execute(
            f"SELECT * FROM memories WHERE id IN ({placeholders})",
            tuple(order),
        ).fetchall()
        edges = connection.execute(
            f"""
            SELECT source, target, relation FROM edges
            WHERE source IN ({placeholders}) AND target IN ({placeholders})
            ORDER BY source, target, relation
            """,
            tuple(order) + tuple(order),
        ).fetchall()
    by_id = {row["id"]: _memory(row) for row in nodes}
    return {
        "nodes": [by_id[memory_id] for memory_id in order if memory_id in by_id],
        "edges": [dict(row) for row in edges],
    }


def _connect(path: str | Path) -> sqlite3.Connection:
    target = Path(path)
    if not str(target):
        raise ValueError("database path is required")
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def _required(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    resolved = " ".join(value.split())
    if not resolved:
        raise ValueError(f"{field} must not be empty")
    resolved.encode("utf-8")
    return resolved


def _tags(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        tag = _required(str(value), "tag")
        if tag not in output:
            output.append(tag)
    return output


def _tokens(value: str) -> list[str]:
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "content": row["content"],
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clonamic-memory")
    sub = parser.add_subparsers(dest="action", required=True)
    save = sub.add_parser("store")
    save.add_argument("--db", required=True)
    save.add_argument("--id", required=True)
    save.add_argument("--content", required=True)
    save.add_argument("--tag", action="append", default=[])
    search = sub.add_parser("recall")
    search.add_argument("--db", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)
    remove = sub.add_parser("forget")
    remove.add_argument("--db", required=True)
    remove.add_argument("--id", required=True)
    edge = sub.add_parser("link")
    edge.add_argument("--db", required=True)
    edge.add_argument("--source", required=True)
    edge.add_argument("--target", required=True)
    edge.add_argument("--relation", required=True)
    view = sub.add_parser("graph")
    view.add_argument("--db", required=True)
    view.add_argument("--anchor", required=True)
    view.add_argument("--depth", type=int, default=2)
    view.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if args.action == "store":
            output: Any = store(args.db, args.id, args.content, args.tag)
        elif args.action == "recall":
            output = recall(args.db, args.query, limit=args.limit)
        elif args.action == "forget":
            output = {"removed": forget(args.db, args.id)}
        elif args.action == "link":
            output = link(args.db, args.source, args.target, args.relation)
        else:
            output = graph(args.db, args.anchor, depth=args.depth, limit=args.limit)
        print(json.dumps({"ok": True, "result": output}, ensure_ascii=False, sort_keys=True))
        return 0
    except (TypeError, ValueError, KeyError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

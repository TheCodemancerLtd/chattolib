#!/usr/bin/env python3
"""RoboChatto — a simple command bot for Chatto."""

import asyncio
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import httpx

from chattolib.client import ChattoClient
from chattolib.subscriptions import subscribe_space_events
from chattolib.types import PresenceStatus

START_TIME = time.monotonic()
DB_PATH = os.environ.get("ROBOCHATTO_DB", "robochatto.db")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "https://ollama.f3l1x.it")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5")

COMMANDS = {
    "/rc:help": "This is a bot created by Felix (and Claude). Use `/rc:commands` to see available commands.",
    "/rc:shrug": "¯\\_(ツ)_/¯",
}


def init_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS command_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_login TEXT NOT NULL,
            space_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            command TEXT NOT NULL,
            response TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tiers (
            name TEXT PRIMARY KEY,
            level INTEGER NOT NULL UNIQUE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_tiers (
            user_login TEXT PRIMARY KEY,
            tier TEXT NOT NULL REFERENCES tiers(name)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS command_tiers (
            command TEXT PRIMARY KEY,
            tier TEXT NOT NULL REFERENCES tiers(name)
        )
    """)
    # Seed default tiers if empty
    if db.execute("SELECT COUNT(*) FROM tiers").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO tiers (name, level) VALUES (?, ?)",
            [("admin", 0), ("premium", 1), ("basic", 2), ("bot", 3)],
        )
    # Seed default user tiers if empty
    if db.execute("SELECT COUNT(*) FROM user_tiers").fetchone()[0] == 0:
        db.executemany(
            "INSERT OR IGNORE INTO user_tiers (user_login, tier) VALUES (?, ?)",
            [("felix", "admin"), ("RoboChatto", "bot"), ("chattobot", "bot")],
        )
    # Seed default command tiers if empty
    if db.execute("SELECT COUNT(*) FROM command_tiers").fetchone()[0] == 0:
        db.executemany(
            "INSERT OR IGNORE INTO command_tiers (command, tier) VALUES (?, ?)",
            [("/rc:commands", "basic"), ("/rc:help", "basic"), ("/rc:shrug", "basic"), ("/rc:uptime", "basic"), ("/rc:prompt", "premium")],
        )
    db.commit()
    return db


def check_permission(db: sqlite3.Connection, command: str, user_login: str) -> str | None:
    """Check if a user's tier level is <= the command's required tier level.

    Returns None if allowed, or the required tier name if denied.
    No command_tiers row = open to all. No user_tiers row = treated as basic.
    """
    row = db.execute(
        "SELECT t.level, t.name FROM command_tiers ct JOIN tiers t ON t.name = ct.tier WHERE ct.command = ?",
        (command,),
    ).fetchone()
    if row is None:
        return None  # no restriction on this command
    required_level, required_tier = row

    row = db.execute(
        "SELECT t.level FROM user_tiers ut JOIN tiers t ON t.name = ut.tier WHERE ut.user_login = ?",
        (user_login,),
    ).fetchone()
    if row is None:
        user_level = db.execute("SELECT level FROM tiers WHERE name = 'basic'").fetchone()[0]
    else:
        user_level = row[0]

    if user_level <= required_level:
        return None
    return required_tier


def log_command(
    db: sqlite3.Connection,
    *,
    user_id: str,
    user_login: str,
    space_id: str,
    room_id: str,
    command: str,
    response: str,
) -> None:
    db.execute(
        "INSERT INTO command_log (timestamp, user_id, user_login, space_id, room_id, command, response) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), user_id, user_login, space_id, room_id, command, response),
    )
    db.commit()


async def query_ollama(prompt: str) -> str:
    """Send a prompt to the Ollama-compatible API and return the response."""
    async with httpx.AsyncClient(timeout=120) as http:
        resp = await http.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": "Do not use markdown headlines (lines starting with #). Use **bold** for emphasis instead."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def handle_event(client: ChattoClient, db: sqlite3.Connection, event: dict) -> None:
    inner = event.get("event", {})
    body = inner.get("body", "")
    if not body:
        return

    cmd = body.strip()
    # Extract the command name (first word) for prefix commands
    cmd_name = cmd.split()[0] if cmd.split() else cmd

    space_id = inner["spaceId"]
    room_id = inner["roomId"]
    event_id = event.get("id")
    in_thread = inner.get("inThread")
    actor = event.get("actor", {})
    user_id = actor.get("id", "?")
    user_login = actor.get("login", "?")

    if cmd_name == "/rc:commands":
        rows = db.execute(
            "SELECT ct.command, ct.tier FROM command_tiers ct ORDER BY ct.command"
        ).fetchall()
        lines = ["**Available commands:**"]
        for command, tier in rows:
            lines.append(f"- `{command}` — {tier}+")
        response = "\n".join(lines)
    elif cmd_name == "/rc:uptime":
        elapsed = int(time.monotonic() - START_TIME)
        days, rem = divmod(elapsed, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        response = f"Uptime: {' '.join(parts)}"
    elif cmd_name == "/rc:prompt":
        prompt_text = cmd[len("/rc:prompt"):].strip()
        if not prompt_text:
            response = "Usage: /rc:prompt <your question>"
        else:
            await client.add_reaction(space_id, room_id, event_id, "hourglass_flowing_sand")
            try:
                response = await query_ollama(prompt_text)
            except Exception as e:
                print(f"[{user_login}] {cmd_name} → error: {e}", flush=True)
                response = "Something went wrong."
            finally:
                try:
                    await client.remove_reaction(space_id, room_id, event_id, "hourglass_flowing_sand")
                except Exception:
                    pass
    else:
        response = COMMANDS.get(cmd)
    if response is None:
        return

    denied_tier = check_permission(db, cmd_name, user_login)
    if denied_tier is not None:
        print(f"[{user_login}] {cmd_name} → denied (requires {denied_tier} tier)")
        await client.post_message(
            space_id, room_id,
            f"Access denied. `{cmd_name}` requires **{denied_tier}** tier or above.",
            in_reply_to=event_id,
            in_thread=in_thread,
        )
        return

    print(f"[{user_login}] {cmd} → replying in {room_id}")
    await client.post_message(space_id, room_id, response, in_reply_to=event_id, in_thread=in_thread)

    log_command(
        db,
        user_id=user_id,
        user_login=user_login,
        space_id=space_id,
        room_id=room_id,
        command=cmd,
        response=response,
    )


async def main() -> None:
    login = os.environ.get("CHATTO_LOGIN")
    password = os.environ.get("CHATTO_PASSWORD")
    if not login or not password:
        print("Set CHATTO_LOGIN and CHATTO_PASSWORD environment variables", file=sys.stderr)
        sys.exit(1)

    db = init_db()
    print(f"Database: {DB_PATH}")

    client = await ChattoClient.login(login, password)
    async with client:
        me = await client.me()
        print(f"Logged in as {me.login} (id={me.id})")

        await client.update_presence(PresenceStatus.ONLINE)
        print("Presence set to ONLINE")

        spaces = await client.spaces()
        if not spaces:
            print("No spaces found", file=sys.stderr)
            sys.exit(1)

        print(f"Listening on {len(spaces)} space(s):")
        for s in spaces:
            print(f"  - {s.name} ({s.id})")

        # Subscribe to all spaces + keep presence alive
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(presence_keepalive(client))
                for space in spaces:
                    tg.create_task(listen_space(client, db, space.id, space.name))
        finally:
            print("Shutting down (disconnecting sets presence to offline)")
            db.close()


async def presence_keepalive(client: ChattoClient) -> None:
    """Re-send ONLINE presence every 60s to stay visible in the user list."""
    while True:
        try:
            await asyncio.sleep(60)
            await client.update_presence(PresenceStatus.ONLINE)
        except Exception as e:
            print(f"[presence] Error: {e}")
            await asyncio.sleep(10)


async def listen_space(
    client: ChattoClient, db: sqlite3.Connection, space_id: str, space_name: str
) -> None:
    while True:
        try:
            async for event in subscribe_space_events(
                client._url, client._token, space_id
            ):
                await handle_event(client, db, event)
        except Exception as e:
            print(f"[{space_name}] Connection lost: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())

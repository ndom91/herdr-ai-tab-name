#!/usr/bin/env python3
"""Rename a focused Herdr tab from its pane context."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tomllib
import urllib.request
from contextlib import contextmanager
from pathlib import Path

SHELLS = {"bash", "fish", "sh", "zsh"}
PREFIX_APPS = {"claude", "codex", "nvim", "opencode", "vim"}
DEFAULT_PROMPT = """You are naming a terminal tab based on its terminal content.
Return only a concise 2-3 word kebab-case title. Prefer the current Git branch's
task intent. If it is main or master, describe the project and current work."""


def herdr(*args: str) -> dict:
    result = subprocess.run(
        [os.environ.get("HERDR_BIN_PATH", "herdr"), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)["result"]
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Herdr response for {' '.join(args)}: {result.stdout[:120]!r}") from error


def herdr_text(*args: str) -> str:
    return subprocess.run(
        [os.environ.get("HERDR_BIN_PATH", "herdr"), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def load_config() -> dict:
    config_dir = Path(os.environ["HERDR_PLUGIN_CONFIG_DIR"])
    path = config_dir / "config.toml"
    if not path.exists():
        raise RuntimeError(f"missing configuration: copy config.example.toml to {path}")
    with path.open("rb") as config_file:
        config = tomllib.load(config_file)
    if config.get("llm", {}).get("api_key"):
        raise RuntimeError("move llm.api_key from config.toml to secrets.toml before using the plugin")
    secrets_path = config_dir / "secrets.toml"
    if secrets_path.exists():
        with secrets_path.open("rb") as secrets_file:
            secrets = tomllib.load(secrets_file)
        if api_key := secrets.get("llm", {}).get("api_key"):
            config.setdefault("llm", {})["api_key"] = api_key
    return config


def api_key(config: dict) -> str:
    return os.environ.get("HERDR_AI_TAB_NAME_API_KEY") or config["llm"].get("api_key", "")


def tab_id_from(value: object) -> str | None:
    if isinstance(value, dict):
        tab_id = value.get("tab_id")
        if isinstance(tab_id, str):
            return tab_id
        for child in value.values():
            if found := tab_id_from(child):
                return found
    if isinstance(value, list):
        for child in value:
            if found := tab_id_from(child):
                return found
    return None


def target_tab_id() -> str:
    for variable in ("HERDR_PLUGIN_EVENT_JSON", "HERDR_PLUGIN_CONTEXT_JSON"):
        raw = os.environ.get(variable)
        if raw:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if tab_id := tab_id_from(event):
                return tab_id
    if tab_id := os.environ.get("HERDR_TAB_ID"):
        return tab_id
    raise RuntimeError("Herdr did not provide a target tab")


def git_branch(cwd: str) -> str:
    result = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def process_name(pane_id: str) -> str:
    info = herdr("pane", "process-info", "--pane", pane_id)["process_info"]
    processes = info.get("foreground_processes", [])
    return processes[0].get("name", "") if processes else ""


def tab_panes(tab_id: str) -> list[dict]:
    workspace_id = tab_id.split(":", 1)[0]
    panes = herdr("pane", "list", "--workspace", workspace_id)["panes"]
    return [pane for pane in panes if pane["tab_id"] == tab_id]


def metadata(panes: list[dict]) -> tuple[str, list[str]]:
    rows = []
    commands = []
    for pane in panes:
        command = process_name(pane["pane_id"])
        cwd = pane.get("foreground_cwd") or pane["cwd"]
        branch = git_branch(cwd)
        rows.append(f"{command}:{cwd}:{branch}")
        commands.append(command)
    return "\n".join(rows), commands


def plain_shell_title(panes: list[dict], commands: list[str]) -> str | None:
    if not panes or any(command not in SHELLS for command in commands):
        return None
    cwd = panes[0].get("foreground_cwd") or panes[0]["cwd"]
    return "home" if cwd == str(Path.home()) else Path(cwd).name


def app_prefix(panes: list[dict], commands: list[str]) -> str:
    for pane, command in zip(panes, commands, strict=True):
        if command in PREFIX_APPS:
            return command
        if agent := pane.get("agent"):
            if agent in PREFIX_APPS:
                return agent
    return ""


def pane_content(panes: list[dict], line_count: int) -> str:
    parts = []
    for pane in panes:
        output = herdr_text(
            "pane", "read", pane["pane_id"], "--source", "recent-unwrapped", "--lines", str(line_count)
        )
        parts.append(f"[Pane: cwd={pane.get('foreground_cwd') or pane['cwd']}]\n{output}")
    return "\n---\n".join(parts)


def title_prompt(config: dict) -> str:
    rename = config.get("rename", {})
    prompt = DEFAULT_PROMPT
    if (max_chars := rename.get("max_title_chars")) is not None:
        prompt += f" Keep the title to at most {max_chars} characters."
    if (max_words := rename.get("max_title_words")) is not None:
        prompt += (
            f" Aim for at most {max_words} words; hyphen-separated title parts count as words "
            "(for example, refactor-react-effect is 3 words)."
        )
    return prompt


def generate_title(content: str, config: dict) -> str:
    llm = config["llm"]
    key = api_key(config)
    payload = json.dumps(
        {
            "model": llm["model"],
            "messages": [
                {"role": "system", "content": title_prompt(config)},
                {"role": "user", "content": content},
            ],
            "temperature": 0.3,
            "max_tokens": 30,
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    ssl_verify = llm.get("ssl_verify", True)
    context = ssl.create_default_context(cafile=ssl_verify) if isinstance(ssl_verify, str) else None
    if ssl_verify is False:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(llm["url"], data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"].strip().strip("`\"' ")


def normalize(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    if not words:
        raise RuntimeError("LLM returned no kebab-case title")
    return "-".join(words[:4])


def trim_title(title: str, max_chars: int | None) -> str:
    if max_chars is None:
        return title
    return title[:max_chars].rstrip("-")


def cache_path(tab_id: str) -> Path:
    state_dir = Path(os.environ["HERDR_PLUGIN_STATE_DIR"])
    return state_dir / "cache" / f"{tab_id.replace(':', '-')}.json"


def save_cache(tab_id: str, value: dict) -> None:
    path = cache_path(tab_id)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(value))
    temporary_path.replace(path)


@contextmanager
def locked_tab_cache(tab_id: str) -> dict:
    state_dir = Path(os.environ["HERDR_PLUGIN_STATE_DIR"])
    cache_dir = state_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_tab_id = tab_id.replace(":", "-")
    lock_path = cache_dir / f"{safe_tab_id}.lock"
    path = cache_path(tab_id)
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            try:
                cache = json.loads(path.read_text()) if path.exists() else {}
            except json.JSONDecodeError:
                cache = {}
            yield cache
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def rename(force: bool) -> None:
    tab_id = target_tab_id()
    with locked_tab_cache(tab_id) as cached:
        config = load_config()
        panes = tab_panes(tab_id)
        fingerprint, commands = metadata(panes)
        rename_config = config.get("rename", {})
        fingerprint += (
            f"\nmax_title_chars={rename_config.get('max_title_chars')!r}"
            f"\nmax_title_words={rename_config.get('max_title_words')!r}"
        )
        digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        if not force and cached and cached["digest"] == digest:
            title = cached["title"]
            herdr("tab", "rename", tab_id, title)
            return
        title = plain_shell_title(panes, commands)
        if title is None:
            line_count = config.get("rename", {}).get("max_lines_per_pane", 40)
            title = generate_title(pane_content(panes, line_count), config)
            if prefix := app_prefix(panes, commands):
                title = f"{prefix}:{title.removeprefix(prefix + ':').removeprefix(prefix + '-')}"
        title = trim_title(normalize(title.replace(":", "-")), rename_config.get("max_title_chars"))
        save_cache(tab_id, {"digest": digest, "title": title})
        herdr("tab", "rename", tab_id, title)


def main() -> None:
    try:
        rename("--force" in sys.argv)
    except Exception as error:
        print(f"herdr-ai-tab-name: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

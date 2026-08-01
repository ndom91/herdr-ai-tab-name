# herdr-ai-tab-name

Automatically rename focused Herdr tabs with short dash-case names from pane context. It uses an OpenAI-compatible local LLM and is inspired by `tmux-ai-window-name`.

## What it does

- Runs only when a tab receives focus, or when the `refresh` plugin action is invoked.
- Caches by foreground command, working directory, and Git branch. Revisiting an unchanged tab makes no LLM call.
- Uses the directory name when every pane is an idle shell.
- Reads recent pane output only on a cache miss.
- Prefixes names for known apps such as `claude`, `opencode`, and `nvim`.

## Install

```sh
herdr plugin link /opt/ndomino/herdr-ai-tab-name
config_dir="$(herdr plugin config-dir ndomino.ai-tab-name)"
cp /opt/ndomino/herdr-ai-tab-name/config.example.toml "$config_dir/config.toml"
cp /opt/ndomino/herdr-ai-tab-name/secrets.example.toml "$config_dir/secrets.toml"
```

Set `llm.url`, `llm.model`, and `llm.ssl_verify` in `config.toml`. Set `llm.api_key` in `secrets.toml`. A non-empty `HERDR_AI_TAB_NAME_API_KEY` takes precedence over the secret file.

You can commit `config.toml` to dotfiles. Keep `secrets.toml` out of version control. The plugin rejects an API key in `config.toml`.

## Refresh action

The plugin exposes `ndomino.ai-tab-name.refresh`, which ignores the cache for the active tab. Bind it in `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "prefix+shift+a"
type = "plugin_action"
command = "ndomino.ai-tab-name.refresh"
description = "refresh AI tab name"
```

Reload the configuration with `Ctrl-a r`.

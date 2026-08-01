# herdr-ai-tab-name

Automatically rename Herdr tabs with short dash-case names from pane context using any local LLM. This is a rewrite of my tmux variant of this same plugin - [`tmux-ai-window-name`](https://github.com/ndom91/tmux-ai-window-name).

![](.github/screenshot_001.png)

## What it does

- Runs name generation when a tab receives focus, or when manually triggered.
- Caches by foreground command, working directory, and Git branch. Revisiting an unchanged tab makes no LLM call.
- Uses the directory name when every pane is an idle shell.
- Reads recent pane output only on a cache miss.
- Prefixes names for known apps such as `claude`, `opencode`, and `nvim`.

## Install

```sh
git clone https://github.com/ndom91/herdr-ai-tab-name
herdr plugin link $(pwd)/herdr-ai-tab-name
config_dir="$(herdr plugin config-dir ndomino.ai-tab-name)"
cp $(pwd)/herdr-ai-tab-name/config.example.toml "$config_dir/config.toml"
cp $(pwd)/herdr-ai-tab-name/secrets.example.toml "$config_dir/secrets.toml"
```

Set `llm.url`, `llm.model`, and `llm.ssl_verify` (optional) in `config.toml`. Set `llm.api_key` in `secrets.toml`. A non-empty `HERDR_AI_TAB_NAME_API_KEY` takes precedence over the secret file.

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

Then reload the configuration with `<leader> shift+a`.

## License

MIT

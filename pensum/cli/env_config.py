"""Env config loader: ``--env prod`` reads connection params from a YAML file.

Search order:
  1. ``$PENSUM_CONFIG_DIR/<env>.yaml`` (if env var set)
  2. ``./.pensum/<env>.yaml``    (project-local; usually .gitignored)
  3. ``~/.pensum/envs/<env>.yaml`` (user-global)

Recognized keys (all optional; CLI flags override):
  url, dialect, auth, token_env, user_env, verify_ssl

The config is merged into the argparse namespace BEFORE the explicit flags
are applied, so explicit flags always win.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from pensum.exceptions import ConfigurationError


CONFIG_KEYS = ("url", "dialect", "auth", "token_env", "user_env", "verify_ssl")


def find_env_config(env_name: str) -> Path | None:
    """Return the first existing config file matching this env name, or None."""
    for candidate in _candidate_paths(env_name):
        if candidate.is_file():
            return candidate
    return None


def _candidate_paths(env_name: str) -> list[Path]:
    paths: list[Path] = []
    custom = os.environ.get("PENSUM_CONFIG_DIR")
    if custom:
        paths.append(Path(custom) / f"{env_name}.yaml")
    paths.append(Path.cwd() / ".pensum" / f"{env_name}.yaml")
    paths.append(Path.home() / ".pensum" / "envs" / f"{env_name}.yaml")
    return paths


def load_env_config(env_name: str) -> dict[str, Any]:
    """Read the YAML file for `env_name`. Empty dict if no config found.
    Raises ConfigurationError on malformed YAML or unknown keys."""
    path = find_env_config(env_name)
    if path is None:
        return {}
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigurationError(f"env config {path!s} is not valid YAML: {e}") from e
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigurationError(
            f"env config {path!s} must be a mapping, got {type(raw).__name__}"
        )
    unknown = set(raw) - set(CONFIG_KEYS)
    if unknown:
        raise ConfigurationError(
            f"env config {path!s} has unknown keys {sorted(unknown)}; "
            f"recognized: {list(CONFIG_KEYS)}"
        )
    return raw


def apply_env_defaults(args: Any, env_name: str | None) -> None:
    """Fill in argparse `args` from the env config IF a flag was not set on
    the command line. Mutates `args` in place.

    Detection of "set on the command line" vs "argparse default" is approximate:
    we check for falsy values (None, empty string, default constant). For
    `verify_ssl`, the default is True; we treat a True value as
    "use config if config disagrees", since the CLI flag is `--no-verify-ssl`
    (negative flag).
    """
    if not env_name:
        return
    cfg = load_env_config(env_name)
    if not cfg:
        return
    for key in ("url", "dialect", "auth", "token_env", "user_env"):
        if key in cfg and not getattr(args, key, None):
            setattr(args, key, cfg[key])
    # verify_ssl semantics: the CLI uses --no-verify-ssl (sets no_verify_ssl=True).
    # The config uses verify_ssl: bool. If config says False, set no_verify_ssl.
    if "verify_ssl" in cfg and not cfg["verify_ssl"]:
        if not getattr(args, "no_verify_ssl", False):
            args.no_verify_ssl = True

#!/usr/bin/env sh
if [ -z "$husky_skip_init" ]; then
  husky_skip_init=1

  command_exists() {
    command -v "$1" >/dev/null 2>&1
  }

  if [ -f "$HOME/.huskyrc" ]; then
    . "$HOME/.huskyrc"
  fi

  export HUSKY=1
  if [ "$HUSKY_DEBUG" = "1" ]; then
    set -x
  fi

  if [ -z "$husky_use_builtin_node" ]; then
    if command_exists pnpm; then
      PATH="$(pnpm bin):$PATH"
    elif command_exists yarn; then
      PATH="$(yarn bin):$PATH"
    elif command_exists npm; then
      PATH="$(npm bin):$PATH"
    fi
  fi

  husky_skip_init=
fi


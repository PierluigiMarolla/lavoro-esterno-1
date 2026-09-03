#!/bin/sh
set -eu

model="${OLLAMA_DEFAULT_MODEL:-gemma4:e2b}"
if ollama show "$model" >/dev/null 2>&1; then
  echo "Ollama model already present: $model"
else
  echo "Downloading Ollama model: $model"
  ollama pull "$model"
fi

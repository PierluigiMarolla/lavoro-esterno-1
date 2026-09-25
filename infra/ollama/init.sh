#!/bin/sh
# Garantisce in modo idempotente che il modello locale predefinito sia presente.
set -eu

model="${OLLAMA_DEFAULT_MODEL:-hf.co/unsloth/gemma-4-E2B-it-GGUF:UD-Q4_K_XL}"
if ollama show "$model" >/dev/null 2>&1; then
  echo "Ollama model already present: $model"
else
  echo "Downloading Ollama model: $model"
  ollama pull "$model"
fi

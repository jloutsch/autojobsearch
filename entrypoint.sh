#!/bin/sh
set -e

# Ensure data directory exists
mkdir -p /app/data

# Pull default Ollama model if not already available
OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434}"
MODEL="${OLLAMA_MODEL:-llama3.2:latest}"

echo "Checking for Ollama model: $MODEL"
if curl -sf "$OLLAMA_URL/api/tags" | grep -q "\"$MODEL\""; then
    echo "Model $MODEL already available"
else
    echo "Pulling model $MODEL (this may take a few minutes on first run)..."
    curl -s "$OLLAMA_URL/api/pull" -d "{\"name\":\"$MODEL\"}" | while read -r line; do
        status=$(echo "$line" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [ -n "$status" ]; then
            printf "\r  %s" "$status"
        fi
    done
    echo ""
    echo "Model pull complete"
fi

echo "Starting dashboard server on port 8080..."
exec python main.py serve 8080

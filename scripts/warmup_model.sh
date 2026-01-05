#!/bin/bash

# Model Warm-up Script for Qwen2.5:32b
# Keeps the LLM model loaded in memory to avoid cold starts

OLLAMA_URL="${OLLAMA_URL:-http://51.112.105.60:11434}"
MODEL="qwen2.5:32b"
KEEP_ALIVE="30m"  # Keep model in memory for 30 minutes

echo "🔥 Warming up $MODEL at $OLLAMA_URL"
echo "📊 This will load the model into memory and keep it warm"
echo "⏰ Keep-alive set to: $KEEP_ALIVE"
echo ""

# Send a simple prompt to load the model
curl -s "$OLLAMA_URL/api/generate" -d "{
  \"model\": \"$MODEL\",
  \"prompt\": \"Hello\",
  \"stream\": false,
  \"keep_alive\": \"$KEEP_ALIVE\"
}" > /dev/null

if [ $? -eq 0 ]; then
    echo "✅ Model is now loaded and warm!"
    echo "⚡ Subsequent requests will be fast (~0.2-0.3s first token)"
    echo "🕐 Model will stay in memory for $KEEP_ALIVE"
else
    echo "❌ Failed to warm up model"
    exit 1
fi

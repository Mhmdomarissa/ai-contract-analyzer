#!/bin/bash

# Automated Model Keep-Alive Service
# Pings the model every 20 minutes to keep it loaded in memory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_URL="${OLLAMA_URL:-http://51.112.105.60:11434}"
MODEL="qwen2.5:32b"
INTERVAL=1200  # 20 minutes (in seconds)

echo "🔄 Starting Model Keep-Alive Service"
echo "📡 Target: $OLLAMA_URL"
echo "🤖 Model: $MODEL"
echo "⏰ Ping interval: ${INTERVAL}s (20 minutes)"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] 🔥 Pinging model to keep it warm..."
    
    RESPONSE=$(curl -s "$OLLAMA_URL/api/generate" -d "{
        \"model\": \"$MODEL\",
        \"prompt\": \"ping\",
        \"stream\": false,
        \"keep_alive\": \"30m\"
    }" 2>&1)
    
    if echo "$RESPONSE" | grep -q "response"; then
        echo "[$TIMESTAMP] ✅ Model is warm and responsive"
    else
        echo "[$TIMESTAMP] ⚠️  Warning: Model ping may have failed"
    fi
    
    echo "[$TIMESTAMP] ⏳ Sleeping for $INTERVAL seconds..."
    echo ""
    sleep $INTERVAL
done

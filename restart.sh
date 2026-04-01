#!/bin/bash
echo "🔄 Stopping old bot..."
pkill -9 -f "python3 main.py" 2>/dev/null || true
fuser -k 5000/tcp 2>/dev/null || true
sleep 3
echo "🚀 Starting ResumePro AI bot..."
python3 main.py &
echo "✅ Bot started in background"
sleep 2
curl -s http://localhost:5000/health | head -1

#!/bin/bash
echo "🔄 Stopping old bot..."
pkill -9 -f "python.*main.py" 2>/dev/null || true
fuser -k 5000/tcp 2>/dev/null || true
sleep 2
echo "🚀 Starting ResumePro AI bot..."
export PYTHONPATH=/home/runner/workspace/.pkgs:$PYTHONPATH
nohup python3 main.py > bot.log 2>&1 &
sleep 3
echo "✅ Bot started"
curl -s http://localhost:5000/health
echo ""
echo "📋 Logs: tail -f bot.log"

#!/bin/bash
echo "🔄 Stopping old bot..."
pkill -f "python3 main.py" || true
sleep 2
echo "🚀 Starting ResumePro AI bot..."
python3 main.py &
echo "✅ Bot started in background"

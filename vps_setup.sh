#!/bin/bash
# Apteka Bot VPS Setup Script
# Run this on the VPS after connecting via SSH

set -e

echo "🚀 Starting Apteka Bot setup..."

# 1. Update system
echo "📦 Updating system..."
apt update && apt upgrade -y

# 2. Install Python and tools
echo "🐍 Installing Python..."
apt install -y python3.11 python3.11-venv python3-pip git

# 3. Clone repository
echo "📥 Cloning repository..."
cd /opt
if [ -d "apteka-bot" ]; then
    echo "Repository exists, pulling latest..."
    cd apteka-bot && git pull
else
    git clone https://github.com/NickStr11/apteka-bot.git
    cd apteka-bot
fi

# 4. Create virtual environment
echo "🔧 Setting up virtual environment..."
python3.11 -m venv .venv
source .venv/bin/activate

# 5. Install dependencies
echo "📚 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Base setup complete!"
echo ""
echo "⚠️  Next steps:"
echo "1. Create .env file: nano /opt/apteka-bot/.env"
echo "2. Copy Google credentials JSON to /opt/apteka-bot/"
echo "3. Create systemd service (see below)"

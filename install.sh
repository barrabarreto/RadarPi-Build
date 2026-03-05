#!/bin/bash

# Cores para o terminal
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}### Iniciando Instalação do RadarPi - Orange Pi Zero ###${NC}"

# 1. Atualizar Sistema e Instalar Dependências do Armbian
echo -e "${GREEN}[1/5] Instalando dependências do sistema...${NC}"
sudo apt update
sudo apt install -y python3-pip python3-dev python3-opencv \
    libopencv-dev tailscale build-essential python3-setuptools \
    git pkg-config

# 2. Instalar Bibliotecas Python
echo -e "${GREEN}[2/5] Instalando bibliotecas Python...${NC}"
pip3 install requests OPi.GPIO opencv-python --break-system-packages

# 3. Configuração do Tailscale
echo -e "${GREEN}[3/5] Configurando Tailscale...${NC}"
read -p "Digite sua Auth Key do Tailscale (deixe vazio para pular): " TAILSCALE_KEY
if [ ! -z "$TAILSCALE_KEY" ]; then
    sudo tailscale up --authkey=$TAILSCALE_KEY
else
    echo "Pulando configuração automática do Tailscale..."
fi

# 4. Configuração Inicial do Radar (Gera o config.json)
echo -e "${GREEN}[4/5] Configuração de Variáveis do Radar...${NC}"
python3 -c "
import json, os
config = {
    'RTSP_URL': input('URL RTSP da Câmera: '),
    'BOT_TOKEN': input('Token do Bot Telegram: '),
    'CHAT_ID': input('ID do Chat Telegram: '),
    'SENSOR_DISTANCE_M': float(input('Distância entre sensores (m) [ex: 2.0]: ') or 2.0),
    'SPEED_LIMIT_KMH': float(input('Limite de Velocidade (km/h) [ex: 30]: ') or 30.0)
}
with open('config.json', 'w') as f:
    json.dump(config, f, indent=4)
"

# 5. Criar Serviço Systemd para rodar em Background
echo -e "${GREEN}[5/5] Criando serviço de inicialização automática...${NC}"
CUR_DIR=$(pwd)
CUR_USER=$(whoami)

SERVICE_FILE="[Unit]
Description=Serviço RadarPi
After=network.target tailscaled.service

[Service]
User=$CUR_USER
WorkingDirectory=$CUR_DIR
ExecStart=/usr/bin/python3 $CUR_DIR/main.py
Restart=always

[Install]
WantedBy=multi-user.target"

echo "$SERVICE_FILE" | sudo tee /etc/systemd/system/radarpi.service
sudo systemctl daemon-reload
sudo systemctl enable radarpi.service

echo -e "${GREEN}### Instalação Concluída! ###${NC}"
echo "O radar iniciará automaticamente no boot. Use 'sudo systemctl start radarpi' para rodar agora."
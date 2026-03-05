# 🏎️ RadarPi-Build (Orange Pi Zero)

Sistema de radar de velocidade utilizando dois sensores infravermelhos (IR) e uma Orange Pi Zero. Ao detectar excesso de velocidade, o sistema captura um frame de uma câmera IP via RTSP e envia para um bot no Telegram.

## 🛠️ Hardware Necessário
* **Orange Pi Zero** (LTS ou normal)
* **2x Sensores de Obstáculo Infravermelho** (Digital)
* **Câmera IP** com suporte a RTSP
* **Fonte 5V 2A**

## 🔌 Conexões (GPIO)
Utilizamos a numeração física dos pinos (BOARD):
| Componente | Pino Físico | GPIO (Pino Armbian) |
| :--- | :--- | :--- |
| Sensor 1 (Entrada) | Pino 7 | PA6 |
| Sensor 2 (Saída) | Pino 11 | PA1 |
| VCC Sensores | Pino 2 ou 4 | 5V |
| GND Sensores | Pino 6 | Ground |

## 🚀 Instalação Rápida

1. Clone o repositório no seu Orange Pi:
```bash
git clone [https://github.com/barrabarreto/RadarPi-Build.git](https://github.com/barrabarreto/RadarPi-Build.git)
cd RadarPi-Build
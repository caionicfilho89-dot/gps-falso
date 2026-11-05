# 🛰️ GPS Falso (simulador NMEA)

Finge um **GPS no PC**. Você escolhe o ponto (ou uma cidade), pode simular **movimento** (rumo+velocidade ou uma rota de pontos) e o app entrega um sinal **NMEA 0183** por **TCP / UDP / arquivo** — aí os programas de navegação/mapas leem como se fosse um GPS de verdade. Tudo offline.

Feito em Python + PyQt6.

## O que faz

- 📍 Escolhe o ponto por **cidade** ou **lat/lon**
- 🚶 Simula **movimento**: parado, andar num **rumo** a uma **velocidade**, ou seguir uma **rota** de pontos (em loop)
- 📡 Entrega o sinal por **TCP** (porta), **UDP** (host:porta) ou **arquivo** `.nmea`
- 🛰️ Gera sentenças padrão **GPGGA** e **GPRMC** (com checksum), à taxa que você escolher (1–10 Hz)
- 👀 Mostra a posição atual e a última sentença enviada

## Como usar

1. Instale a dependência:
   ```
   pip install -r requirements.txt
   ```
2. Rode:
   ```
   pythonw gps_falso.pyw
   ```
3. Escolha o ponto, o movimento e a saída, e clique **Ligar GPS falso**.
4. No programa de navegação, configure a entrada de GPS pra **NMEA via TCP** no `127.0.0.1` porta **10110** (a porta clássica de NMEA).

Programas que aceitam NMEA por TCP/arquivo: OpenCPN, u-center, GpsGate, qMapShack, etc. Alguns leem só porta serial — nesse caso use um par de portas COM virtuais (ex.: com0com) e aponte o arquivo/stream pra lá.

## Como funciona (pra quem tem curiosidade)

A cada tick, o app calcula a posição (parada, ou avançando conforme rumo/velocidade, ou interpolando ao longo da rota pela distância percorrida), monta as sentenças NMEA `GPGGA`+`GPRMC` com o checksum certinho e transmite pela saída escolhida. O servidor TCP aceita vários clientes e manda a cada um.

## Pra que serve

Testar e desenvolver software que usa GPS sem precisar sair andando com um receptor — simular rotas, posições e velocidades. Use com responsabilidade.

## Requisitos

- Windows / Linux / macOS
- Python 3.10+
- `PyQt6`

## Licença

MIT — veja [LICENSE](LICENSE).

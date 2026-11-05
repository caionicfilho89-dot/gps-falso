"""Motor do GPS Falso (simulador NMEA).

Gera sentenças NMEA 0183 (GPGGA + GPRMC) de uma posição escolhida, com opção de simular
movimento (rumo+velocidade ou uma rota de pontos). Entrega o "sinal" por TCP, UDP ou arquivo,
pra programas de navegação/mapas no PC lerem como se fosse um GPS de verdade. Tudo offline.
"""
from __future__ import annotations

import math
import socket
import threading
import time

R_EARTH = 6371000.0  # m


# ---------------- sentenças NMEA ----------------
def checksum(body: str) -> str:
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"{c:02X}"


def _fmt(deg: float, is_lat: bool) -> tuple[str, str]:
    hemi = ("N" if deg >= 0 else "S") if is_lat else ("E" if deg >= 0 else "W")
    deg = abs(deg)
    d = int(deg)
    m = (deg - d) * 60
    if is_lat:
        return f"{d:02d}{m:07.4f}", hemi
    return f"{d:03d}{m:07.4f}", hemi


def gga(lat, lon, alt=10.0, sats=9, hdop=0.9, t=None) -> str:
    t = time.gmtime(t if t is not None else time.time())
    hhmmss = time.strftime("%H%M%S", t)
    la, ns = _fmt(lat, True)
    lo, ew = _fmt(lon, False)
    body = (f"GPGGA,{hhmmss}.00,{la},{ns},{lo},{ew},1,{sats:02d},{hdop:.1f},"
            f"{alt:.1f},M,0.0,M,,")
    return f"${body}*{checksum(body)}"


def rmc(lat, lon, speed_knots=0.0, course=0.0, t=None) -> str:
    tm = time.gmtime(t if t is not None else time.time())
    hhmmss = time.strftime("%H%M%S", tm)
    ddmmyy = time.strftime("%d%m%y", tm)
    la, ns = _fmt(lat, True)
    lo, ew = _fmt(lon, False)
    body = (f"GPRMC,{hhmmss}.00,A,{la},{ns},{lo},{ew},"
            f"{speed_knots:.1f},{course:.1f},{ddmmyy},,,A")
    return f"${body}*{checksum(body)}"


def sentences(lat, lon, speed_kmh=0.0, course=0.0, t=None) -> list[str]:
    kn = speed_kmh / 1.852
    return [gga(lat, lon, t=t), rmc(lat, lon, kn, course, t=t)]


# ---------------- movimento ----------------
def step_heading(lat, lon, speed_kmh, heading_deg, dt):
    """Anda dt segundos na direção heading_deg (0=Norte, 90=Leste)."""
    d = speed_kmh / 3.6 * dt  # metros
    h = math.radians(heading_deg)
    dlat = (d * math.cos(h)) / 111320.0
    dlon = (d * math.sin(h)) / (111320.0 * math.cos(math.radians(lat)) or 1e-9)
    return lat + dlat, lon + dlon


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1, math.sqrt(a)))


class Route:
    """Percorre uma lista de pontos [(lat,lon),...] em loop, a uma velocidade."""

    def __init__(self, points, speed_kmh, loop=True):
        self.points = points
        self.speed_kmh = speed_kmh
        self.loop = loop
        self.i = 0
        self.lat, self.lon = points[0]
        self.course = 0.0
        self.done = False

    def step(self, dt):
        if self.done or len(self.points) < 2:
            return self.lat, self.lon, self.course
        remaining = self.speed_kmh / 3.6 * dt
        while remaining > 0 and not self.done:
            tgt = self.points[(self.i + 1) % len(self.points)]
            dist = haversine(self.lat, self.lon, tgt[0], tgt[1])
            self.course = bearing(self.lat, self.lon, tgt[0], tgt[1])
            if dist <= remaining or dist < 0.5:
                self.lat, self.lon = tgt
                self.i += 1
                remaining -= dist
                if self.i >= len(self.points) - 1 and not self.loop:
                    self.done = True
                if self.loop and self.i >= len(self.points):
                    self.i = 0
            else:
                frac = remaining / dist
                self.lat += (tgt[0] - self.lat) * frac
                self.lon += (tgt[1] - self.lon) * frac
                remaining = 0
        return self.lat, self.lon, self.course


# ---------------- saída ----------------
class TcpServer:
    """Servidor TCP que transmite as linhas NMEA pra todos os clientes conectados."""

    def __init__(self, host="0.0.0.0", port=10110):
        self.host, self.port = host, port
        self._clients = []
        self._lock = threading.Lock()
        self._sock = None
        self._thread = None
        self._run = False

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(5)
        self._run = True
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self):
        while self._run:
            try:
                c, _ = self._sock.accept()
                with self._lock:
                    self._clients.append(c)
            except OSError:
                break

    def broadcast(self, line: str):
        data = (line + "\r\n").encode("ascii", "ignore")
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(data)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)

    def client_count(self):
        with self._lock:
            return len(self._clients)

    def stop(self):
        self._run = False
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


class UdpSender:
    def __init__(self, host="127.0.0.1", port=10110):
        self.addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def broadcast(self, line: str):
        try:
            self._sock.sendto((line + "\r\n").encode("ascii", "ignore"), self.addr)
        except OSError:
            pass

    def client_count(self):
        return 1

    def stop(self):
        try:
            self._sock.close()
        except OSError:
            pass


class FileSink:
    def __init__(self, path):
        self.path = path
        self._f = open(path, "w", encoding="ascii", newline="")

    def broadcast(self, line: str):
        try:
            self._f.write(line + "\r\n")
            self._f.flush()
        except (OSError, ValueError):
            pass

    def client_count(self):
        return 1

    def stop(self):
        try:
            self._f.close()
        except OSError:
            pass

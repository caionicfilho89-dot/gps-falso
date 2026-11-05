"""GPS Falso (simulador NMEA) — finge um GPS no PC. Escolhe o ponto (ou cidade), pode
simular movimento, e entrega o sinal NMEA por TCP/UDP/arquivo pros programas de navegação
lerem como se fosse um GPS real. Tudo offline.
"""
import os
import sys
import time

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nmea  # noqa: E402

ACCENT = "#7c5cff"
CITIES = {
    "São Paulo": (-23.5505, -46.6333), "Rio de Janeiro": (-22.9068, -43.1729),
    "Brasília": (-15.7939, -47.8828), "Nova York": (40.7128, -74.0060),
    "Londres": (51.5074, -0.1278), "Paris": (48.8566, 2.3522),
    "Tóquio": (35.6762, 139.6503), "Lisboa": (38.7223, -9.1393),
}
QSS = """
QWidget { background:#11131a; color:#e7e9f0; font:10pt 'Segoe UI'; }
#title { font:700 18pt 'Segoe UI'; }
#info { color:#8a93a8; }
#big { font:700 13pt 'Consolas','Segoe UI'; color:#79e0a8; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background:#1b202b; border:1px solid #2d3550;
    border-radius:8px; padding:6px; }
QPlainTextEdit { background:#0c0e14; border:1px solid #2d3550; border-radius:10px; color:#79e0a8;
    font:9pt 'Consolas'; }
QPushButton { background:#222a38; border:0; border-radius:10px; padding:9px 14px; }
QPushButton:hover { background:#2d3550; }
#go { background:#7c5cff; color:#fff; font-weight:600; padding:12px 16px; font-size:12pt; }
#go:hover { background:#8f74ff; }
#stop { background:#ff4d4d; color:#fff; font-weight:600; }
"""


def app_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor("transparent"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(14, 10, 36, 36)
    p.setBrush(QColor("#11131a"))
    p.drawEllipse(26, 22, 12, 12)
    p.setBrush(QColor(ACCENT))
    p.drawPolygon(*[QPoint(*q) for q in [(32, 56), (20, 30), (44, 30)]])
    p.end()
    return QIcon(pm)


class GpsFalso(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GPS Falso (simulador NMEA)")
        self.setWindowIcon(app_icon())
        self.resize(560, 620)
        self.sink = None
        self.route = None
        self.lat = -23.5505
        self.lon = -46.6333
        self.course = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(9)
        root.addWidget(QLabel("GPS Falso (simulador NMEA)", objectName="title"))
        root.addWidget(QLabel("Finge um GPS no PC: escolhe o ponto e entrega o sinal (NMEA) pros "
                              "programas de navegação. Offline.", objectName="info"))

        # ponto
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Cidade:"))
        self.city = QComboBox()
        self.city.addItem("— escolher —")
        self.city.addItems(list(CITIES.keys()))
        self.city.currentTextChanged.connect(self._city)
        pr.addWidget(self.city, 1)
        root.addLayout(pr)
        cr = QHBoxLayout()
        cr.addWidget(QLabel("Lat:"))
        self.lat_in = QLineEdit(str(self.lat))
        cr.addWidget(self.lat_in, 1)
        cr.addWidget(QLabel("Lon:"))
        self.lon_in = QLineEdit(str(self.lon))
        cr.addWidget(self.lon_in, 1)
        root.addLayout(cr)

        # movimento
        mr = QHBoxLayout()
        mr.addWidget(QLabel("Movimento:"))
        self.mode = QComboBox()
        self.mode.addItems(["Parado", "Andar (rumo + velocidade)", "Rota (lista de pontos)"])
        self.mode.currentIndexChanged.connect(self._mode)
        mr.addWidget(self.mode, 1)
        root.addLayout(mr)

        self.mov = QWidget()
        mv = QHBoxLayout(self.mov)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.addWidget(QLabel("Rumo°:"))
        self.heading = QDoubleSpinBox()
        self.heading.setRange(0, 359.9)
        mv.addWidget(self.heading)
        mv.addWidget(QLabel("Veloc. km/h:"))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0, 1000)
        self.speed.setValue(40)
        mv.addWidget(self.speed)
        mv.addStretch(1)
        root.addWidget(self.mov)

        self.route_box = QPlainTextEdit()
        self.route_box.setPlaceholderText("um ponto por linha: lat,lon\n-23.5505,-46.6333\n-23.5400,-46.6300")
        self.route_box.setMaximumHeight(90)
        self.route_box.hide()
        root.addWidget(self.route_box)

        # saída
        sr = QHBoxLayout()
        sr.addWidget(QLabel("Enviar por:"))
        self.out = QComboBox()
        self.out.addItems(["TCP (porta)", "UDP (host:porta)", "Arquivo"])
        self.out.currentIndexChanged.connect(self._out)
        sr.addWidget(self.out, 1)
        self.out_arg = QLineEdit("10110")
        sr.addWidget(self.out_arg, 1)
        root.addLayout(sr)

        rr = QHBoxLayout()
        rr.addWidget(QLabel("Taxa (Hz):"))
        self.hz = QSpinBox()
        self.hz.setRange(1, 10)
        self.hz.setValue(1)
        rr.addWidget(self.hz)
        rr.addStretch(1)
        root.addLayout(rr)

        self.pos_lbl = QLabel("", objectName="big")
        root.addWidget(self.pos_lbl)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, 1)

        self.status = QLabel("", objectName="info")
        root.addWidget(self.status)
        self.go = QPushButton("▶  Ligar GPS falso")
        self.go.setObjectName("go")
        self.go.clicked.connect(self.toggle)
        root.addWidget(self.go)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._mode(0)

    # ---- opções ----
    def _city(self, name):
        if name in CITIES:
            self.lat_in.setText(str(CITIES[name][0]))
            self.lon_in.setText(str(CITIES[name][1]))

    def _mode(self, i):
        self.mov.setVisible(i == 1)
        self.route_box.setVisible(i == 2)

    def _out(self, i):
        self.out_arg.setText(["10110", "127.0.0.1:10110", ""][i])
        if i == 2:
            self.out_arg.setPlaceholderText("caminho do arquivo .nmea")

    # ---- ligar/desligar ----
    def _make_sink(self):
        kind = self.out.currentIndex()
        arg = self.out_arg.text().strip()
        if kind == 0:
            return nmea.TcpServer(port=int(arg or 10110))
        if kind == 1:
            host, _, port = arg.partition(":")
            return nmea.UdpSender(host or "127.0.0.1", int(port or 10110))
        if not arg:
            raise ValueError("Escolha um arquivo de saída.")
        return nmea.FileSink(arg)

    def toggle(self):
        if self.timer.isActive():
            self.stop()
            return
        try:
            self.lat = float(self.lat_in.text())
            self.lon = float(self.lon_in.text())
        except ValueError:
            QMessageBox.warning(self, "Ops", "Latitude/longitude inválidas.")
            return
        # rota
        self.route = None
        if self.mode.currentIndex() == 2:
            pts = []
            for ln in self.route_box.toPlainText().splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    a, b = ln.split(",")
                    pts.append((float(a), float(b)))
                except ValueError:
                    QMessageBox.warning(self, "Rota", f"Linha inválida: {ln}")
                    return
            if len(pts) < 2:
                QMessageBox.warning(self, "Rota", "Coloque pelo menos 2 pontos.")
                return
            self.route = nmea.Route(pts, self.speed.value() or 40)
            self.lat, self.lon = pts[0]
        try:
            self.sink = self._make_sink()
            if hasattr(self.sink, "start"):
                self.sink.start()
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "Saída", str(e))
            return
        self.timer.setInterval(int(1000 / self.hz.value()))
        self._last = time.time()
        self.timer.start()
        self.go.setText("■  Desligar")
        self.go.setObjectName("stop")
        self.setStyleSheet(QSS)

    def stop(self):
        self.timer.stop()
        if self.sink:
            self.sink.stop()
            self.sink = None
        self.go.setText("▶  Ligar GPS falso")
        self.go.setObjectName("go")
        self.setStyleSheet(QSS)
        self.status.setText("Desligado.")

    def _tick(self):
        now = time.time()
        dt = now - getattr(self, "_last", now)
        self._last = now
        spd = 0.0
        if self.mode.currentIndex() == 1:
            spd = self.speed.value()
            self.course = self.heading.value()
            self.lat, self.lon = nmea.step_heading(self.lat, self.lon, spd, self.course, dt)
        elif self.mode.currentIndex() == 2 and self.route:
            self.lat, self.lon, self.course = self.route.step(dt)
            spd = self.route.speed_kmh
        for line in nmea.sentences(self.lat, self.lon, spd, self.course):
            self.sink.broadcast(line)
        self.pos_lbl.setText(f"{self.lat:.5f}, {self.lon:.5f}   rumo {self.course:.0f}°   {spd:.0f} km/h")
        self.log.setPlainText(f"{nmea.sentences(self.lat, self.lon, spd, self.course)[1]}")
        n = self.sink.client_count()
        self.status.setText(f"Transmitindo… {('clientes: '+str(n)) if self.out.currentIndex()==0 else 'ok'}")

    def closeEvent(self, e):
        self.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = GpsFalso()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

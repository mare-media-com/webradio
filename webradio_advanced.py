import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkFont
import subprocess
import sys
import datetime
import time
import os
import json
import socket
import requests
import io
from PIL import Image, ImageDraw, ImageFont, ImageTk
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


# region Global Settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----- Radiosender -----
stations = {
    "R.SH": {
        "url": "https://streams.rsh.de/rsh-live/mp3-128/streams.rsh.de/",
        "logo": "img/rsh.png"
    },
    "Q-Dance": {
        "url": "http://playerservices.streamtheworld.com/api/livestream-redirect/Q_DANCE.mp3",
        "logo": "img/qdance.png"
    },
    "NDR 2 SH": {
        "url": "https://icecast.ndr.de/ndr/ndr2/schleswigholstein/mp3/128/stream.mp3",
        "logo": "img/ndr2schleswigholstein.png"
    },
    "Beats Radio": {
        "url": "http://live.streams.klassikradio.de/beats-radio/stream/mp3",
        "logo": "img/beatsradio.png"
    },
    "Ibiza Global Radio": {
        "url": "http://ibizaglobalradio.streaming-pro.com:8024/listen.pls?sid=1",
        "logo": "img/ibizaglobalradio.png"
    },
    "Psyradio Psytrance": {
        "url": "http://streamer.psyradio.org:8030/psytrance/",
        "logo": "img/psyradiopsytrance.png"
    },
    "Psyradio Progressive": {
        "url": "http://streamer.psyradio.org:8010/progressive/",
        "logo": "img/psyradioprogressive.png"
    }
}

# Absoluter Pfad zur .env-Datei relativ zum Skript
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# API-Key aus Umgebungsvariable
WEATHER_API_KEY = os.getenv("OWM_KEY")

# ----- Variablen -----
player_process = None
current_volume = 50
mpv_socket_path = "/tmp/mpv-socket"
last_station_file = "/home/pi/webradio/last_station.txt"
last_station_name = None
current_station_name = ""
active_control = None
muted = False
last_volume_before_mute = current_volume
WEATHER_LAT = "54.80797555"
WEATHER_LON = "9.52438474"
WEATHER_EXCL = "minutely,hourly,daily,alerts"

load_dotenv()
# endregion


# region MPV-Player

# ----- IPC-Kommunikation -----
class MPV:
    def __init__(self, socket_path, process_getter):
        self.socket_path = socket_path
        self.process_getter = process_getter  # Funktion, die den aktuellen mpv-Prozess liefert

    def send(self, command):
        # Nur senden, wenn Prozess läuft
        proc = self.process_getter()
        if proc is None or proc.poll() is not None:
            return  # mpv läuft nicht → Befehl ignorieren

        if not os.path.exists(self.socket_path):
            return  # Socket existiert nicht → Befehl ignorieren

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(self.socket_path)
                s.send((json.dumps(command) + "\n").encode())
        except Exception:
            pass  # Broken pipe vermeiden

    def set_volume(self, vol):
        self.send({"command": ["set_property", "volume", vol]})
        volume_var.set(int(vol))  # GUI-Zahl aktualisieren

mpv = MPV(mpv_socket_path, lambda: player_process)
# endregion


# region Funktionen

def load_icon(filename, size=(48, 48)):
    path = os.path.join(BASE_DIR, "img", filename)
    img = Image.open(path)
    img = img.resize(size, Image.LANCZOS)
    return ImageTk.PhotoImage(img)

def update_datetime():
    """Aktualisiert das Datum und die Uhrzeit im Header."""
    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                  "Freitag", "Samstag", "Sonntag"]
    jetzt = datetime.now()
    wochentag_de = wochentage[jetzt.weekday()]
    
    # Text für Anzeige zusammenstellen
    datetime_text = f"📅 {wochentag_de}, {jetzt.day:02d}.{jetzt.month:02d}.{jetzt.year}  🕒 {jetzt.hour:02d}:{jetzt.minute:02d} Uhr"
    #⏰

    # Variable aktualisieren
    datetime_var.set(datetime_text)
    
    # Alle 10 Sekunden erneut aufrufen
    root.after(10000, update_datetime)

def ms_to_bft(speed_ms):
    """m/s → Beaufort"""
    scale = [0.3,1.5,3.3,5.5,7.9,10.7,13.8,17.1,20.7,24.4,28.4,32.6]
    for i, val in enumerate(scale):
        if speed_ms <= val:
            return i
    return 12

def update_weather():
    """Aktualisiert Temperatur, Beschreibung und farbiges Icon von OpenWeather."""
    try:
        url = (
            f"https://api.openweathermap.org/data/3.0/onecall"
            f"?lat={WEATHER_LAT}"
            f"&lon={WEATHER_LON}"
            f"&exclude={WEATHER_EXCL}"
            f"&appid={WEATHER_API_KEY}"
            f"&units=metric"
            f"&lang=de"
        )

        response = requests.get(url, timeout=5)
        data = response.json()

        # Temperatur, Beschreibung, Icon
        temp = round(data["current"]["temp"])
        desc = data["current"]["weather"][0]["description"]
        icon_code = data["current"]["weather"][0]["icon"]

        # --- PNG Icon setzen ---
        icon_photo = weather_icon_images.get(icon_code)

        if icon_photo:
            weather_icon_label.config(image=icon_photo)
            weather_icon_label.image = icon_photo
        else:
            weather_icon_label.config(image="")

        # Wind
        wind_deg = data["current"]["wind_deg"]
        wind_speed = data["current"]["wind_speed"]
        # Windböen (falls vorhanden)
        gust_speed = data["current"].get("wind_gust", wind_speed)
        gust_bft = ms_to_bft(gust_speed)
        # Beaufort berechnen
        if wind_speed < 0.3: bft = 0
        elif wind_speed < 1.6: bft = 1
        elif wind_speed < 3.4: bft = 2
        elif wind_speed < 5.5: bft = 3
        elif wind_speed < 8.0: bft = 4
        elif wind_speed < 10.8: bft = 5
        elif wind_speed < 13.9: bft = 6
        elif wind_speed < 17.2: bft = 7
        elif wind_speed < 20.8: bft = 8
        elif wind_speed < 24.5: bft = 9
        elif wind_speed < 28.5: bft = 10
        elif wind_speed < 32.7: bft = 11
        else: bft = 12

        # Druck & Luftfeuchtigkeit
        pressure = data["current"]["pressure"]
        humidity = data["current"]["humidity"]

        # --- Variablen aktualisieren ---
        weather_temp_var.set(f"{temp}°C")
        # Windrose rotieren
        angle = (wind_deg + 180) % 360  # +180° für Richtung, %360 für Kreis  # OpenWeather liefert Grad 0-360, 0=Norden
        rotated_img = wind_rose_base_img.rotate(-angle, resample=Image.BICUBIC, expand=True)

        # In PhotoImage umwandeln für Tkinter
        wind_photo = ImageTk.PhotoImage(rotated_img)
        weather_wind_label.config(image=wind_photo)
        weather_wind_label.image = wind_photo  # Referenz halten

        # Beaufort-Wert daneben aktualisieren
        bft_label.config(text=f"{bft} bft")

        # --- Windwarnsymbol setzen ---
        if 5 <= gust_bft <= 7:
            wind_warning_label.config(image=wind_icon_small)
            wind_warning_label.image = wind_icon_small

        elif 8 <= gust_bft <= 9:
            wind_warning_label.config(image=sturm_icon)
            wind_warning_label.image = sturm_icon

        elif 10 <= gust_bft <= 12:
            wind_warning_label.config(image=orkan_icon)
            wind_warning_label.image = orkan_icon

        else:
            wind_warning_label.config(image="")

        if gust_bft >= 10:
            bft_label.config(fg="#ff4444")
        else:
            bft_label.config(fg="white")

        weather_desc_var.set(desc.capitalize())
        pressure_label_text.config(text=f"{pressure} hPa")
        humidity_label_text.config(text=f"{humidity}%")

        # --- Canvas-Breite anpassen ---
        root.update_idletasks()

        text_width = weather_text_frame.winfo_reqwidth()

        langloch_width = icon_size + extra_width + text_width + padding + (radius * 2)

        # Canvas Breite ändern
        weather_canvas.config(width=langloch_width)

        # ✅ Hintergrund GEOMETRISCH korrekt verschieben
        weather_canvas.coords(weather_bg_rect,
            radius, 0,
            langloch_width - radius, langloch_height
        )

        weather_canvas.coords(weather_bg_left,
            0, 0,
            radius * 2, langloch_height
        )

        weather_canvas.coords(weather_bg_right,
            langloch_width - radius * 2, 0,
            langloch_width, langloch_height
        )

        # Content mittig halten
        weather_canvas.coords(weather_window,
            langloch_width // 2,
            langloch_height // 2
        )

    except Exception as e:
        weather_temp_var.set("--°C")
        weather_desc_var.set("Wetterdaten Fehler")
        # weather_wind_var.set("")
        # weather_details_var.set("")
        print("Weather update error:", e)

    # alle 10 Minuten wiederholen
    root.after(600000, update_weather)  # 600000 = alle 10 Minuten

def play_station(name, url):
    global player_process, last_station_name, current_station_name
    last_station_name = name
    current_station_name = name
    now_playing_var.set(f"Jetzt läuft: {current_station_name}")
    stop_station()
    
    # Klinkenausgang aktivieren
    subprocess.call([
        "pactl", "set-default-sink",
        "alsa_output.platform-bcm2835_audio.analog-stereo"
    ])

    # mpv starten
    if os.path.exists(mpv_socket_path):
        os.remove(mpv_socket_path)
    player_process = subprocess.Popen([
        "mpv",
        "--no-video",
        f"--volume={current_volume}",
        f"--input-ipc-server={mpv_socket_path}",
        url
    ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)

    # kurz warten, bis Socket bereit ist
    for _ in range(10):
        if os.path.exists(mpv_socket_path):
            break
        time.sleep(0.1)
    save_last_station(name)
    highlight_active_station(name)
    update_control_highlight()

def highlight_active_station(active_name):
    for name, btn in buttons.items():
        if name == active_name:
            btn.config(highlightbackground="#22aa22", highlightthickness=5)  # #22aa22=grün #FFC200=gelb
        else:
            btn.config(highlightbackground="#222", highlightthickness=1)       # neutral

def update_now_playing():
    """Liest den aktuellen ICY-Titel aus mpv und zeigt den Sendernamen, falls kein sinnvoller Titel verfügbar ist."""
    global current_station_name

    # Standardtext: Sendername
    display_text = f"Jetzt läuft: {current_station_name}"

    # Prüfen, ob mpv läuft
    if player_process is None or player_process.poll() is not None:
        now_playing_var.set(display_text)
        root.after(2000, update_now_playing)
        return

    # Prüfen, ob Socket existiert
    if not os.path.exists(mpv_socket_path):
        now_playing_var.set(display_text)
        root.after(2000, update_now_playing)
        return

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(mpv_socket_path)

            command = {"command": ["get_property", "media-title"]}
            s.send((json.dumps(command) + "\n").encode())

            response = s.recv(4096).decode(errors="ignore")
            data = json.loads(response)
            title = data.get("data")

            # Nur anzeigen, wenn ein sinnvoller ICY-Titel vorliegt
            if title:
                title_clean = title.strip()
                if (
                    len(title_clean) > 3
                    and not title_clean.lower().startswith("http")
                    and ".pls" not in title_clean.lower()
                ):
                    display_text = f"Jetzt läuft: 🎵 {title_clean}"

    except Exception:
        # Im Fehlerfall einfach den Sendernamen anzeigen
        pass

    # Nur aktualisieren, wenn sich etwas geändert hat
    if now_playing_var.get() != display_text:
        now_playing_var.set(display_text)

    # alle 2 Sekunden erneut prüfen
    root.after(2000, update_now_playing)

def play_last_station():
    global station_start_index

    if last_station_name and last_station_name in stations:
        play_station(last_station_name, stations[last_station_name]["url"])
        update_control_highlight()

    if last_station_name in stations_list:
        idx = stations_list.index(last_station_name)

        # Ziel: aktiver Sender möglichst mittig (Position 2 oder 3)
        # Position innerhalb der sichtbaren Sender: pos = 1 (Index 0=erste Position)
        middle_pos = VISIBLE_STATIONS // 2  # z.B. 4//2 = 2 → Index 2 = Position 3
        station_start_index = idx - middle_pos

        # Grenzen überprüfen, nicht unter 0 und nicht über das Maximum
        if station_start_index < 0:
            station_start_index = 0
        if station_start_index + VISIBLE_STATIONS > len(stations_list):
            station_start_index = len(stations_list) - VISIBLE_STATIONS

    update_station_buttons()

def stop_station():
    global player_process

    # Socket löschen, bevor mpv beendet wird
    if os.path.exists(mpv_socket_path):
        try:
            os.remove(mpv_socket_path)
        except:
            pass

    # mpv Prozess beenden
    if player_process and player_process.poll() is None:
        player_process.terminate()
        player_process = None

    update_control_highlight()

def create_png_circle_button(canvas, x, y, r, image, command):

    circle = canvas.create_oval(
        x-r, y-r, x+r, y+r,
        outline=""
    )

    img_item = canvas.create_image(x, y, image=image)

    canvas.tag_bind(circle, "<Button-1>", lambda e: command())
    canvas.tag_bind(img_item, "<Button-1>", lambda e: command())

    canvas.tag_bind(circle, "<Enter>", lambda e: canvas.itemconfig(circle))
    canvas.tag_bind(circle, "<Leave>", lambda e: update_control_highlight())

    return circle

def vol_up():
    global current_volume
    current_volume = min(100, current_volume + 5)
    volume_var.set(current_volume)
    mpv.set_volume(current_volume)
    update_volume_style()

def vol_down():
    global current_volume
    current_volume = max(0, current_volume - 5)
    volume_var.set(current_volume)
    mpv.set_volume(current_volume)
    update_volume_style()

def update_volume_style():
    if current_volume < 30:
        volume_bar.config(style="Vol.Low.Horizontal.TProgressbar")
    elif current_volume < 70:
        volume_bar.config(style="Vol.Mid.Horizontal.TProgressbar")
    else:
        volume_bar.config(style="Vol.High.Horizontal.TProgressbar")

def toggle_mute():
    global muted, last_volume_before_mute, current_volume

    if not muted:
        last_volume_before_mute = current_volume
        current_volume = 0
        muted = True
    else:
        current_volume = last_volume_before_mute
        muted = False

    # Lautstärke an MPV übergeben
    mpv.set_volume(current_volume)
    volume_var.set(current_volume)
    update_volume_style()
    update_control_highlight()

def exit_app():
    stop_station()
    root.destroy()
    sys.exit()

def load_last_station():
    try:
        with open(last_station_file, "r") as f:
            name = f.read().strip()
            if name in stations:
                return name
    except FileNotFoundError:
        return None
    return None

def save_last_station(name):
    with open(last_station_file, "w") as f:
        f.write(name)

def update_control_highlight():
    """Aktive Zustände visuell darstellen"""
    normal = "#666666"
    active_green = "#22aa22"
    active_red = "#cc3333"
    
    # Standardfarben setzen
    control_buttons = [
        stop_circle,
        play_circle,
        exit_circle,
        mute_circle,
        vol_down_circle,
        vol_up_circle
    ]
    for btn in control_buttons:
        control_canvas.itemconfig(btn, fill=normal)
    
    # Play / Stop
    if player_process and player_process.poll() is None:
        control_canvas.itemconfig(play_circle, fill=active_green)
    else:
        control_canvas.itemconfig(stop_circle, fill=active_red)
    
    # Mute
    if muted:
        control_canvas.itemconfig(mute_circle, fill=active_red)
# endregion


# region GUI & Header

# ----- GUI -----

root = tk.Tk()
style = ttk.Style()
style.theme_use("default")

# Standardhöhe Lautstärke-Bar (Fallback)
style.configure(
    "TProgressbar",
    thickness=5
)

# Volume-Bar Leise
style.configure(
    "Vol.Low.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#666",
    lightcolor="#666",
    darkcolor="#666",
    bordercolor="#000",
)

# Volume-Bar Mittel
style.configure(
    "Vol.Mid.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#22aa22",
    lightcolor="#22aa22",
    darkcolor="#22aa22",
    bordercolor="#000",
)

# Volume-Bar Laut
style.configure(
    "Vol.High.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#cc3333",
    lightcolor="#cc3333",
    darkcolor="#cc3333",
    bordercolor="#000",
)

root.attributes("-fullscreen", True)
root.configure(bg="#222")

play_icon = load_icon("play.png")
stop_icon = load_icon("stop.png")
exit_icon = load_icon("exit.png")
volume_down_icon = load_icon("volume_down.png", (32, 32))
volume_up_icon = load_icon("volume_up.png", (32, 32))
mute_icon = load_icon("mute.png", (32, 32))
pressure_icon_img = load_icon("pressure.png", size=(20, 20))
humidity_icon_img = load_icon("humidity.png", size=(20, 20))
wind_rose_base_img = Image.open(os.path.join(BASE_DIR, "img", "wind_rose.png")).convert("RGBA")
wind_rose_base_img = wind_rose_base_img.resize((20,20), Image.LANCZOS)
wind_rose_photo = ImageTk.PhotoImage(wind_rose_base_img)
wind_icon_small = ImageTk.PhotoImage(
    Image.open(os.path.join(BASE_DIR, "img/weather_icons/wind.png")).resize((32, 32))
)

sturm_icon = ImageTk.PhotoImage(
    Image.open(os.path.join(BASE_DIR, "img/weather_icons/sturm.png")).resize((32, 32))
)

orkan_icon = ImageTk.PhotoImage(
    Image.open(os.path.join(BASE_DIR, "img/weather_icons/orkan.png")).resize((32, 32))
)
volume_var = tk.IntVar()
volume_var.set(50)  # Startwert der Lautstärke (z.B. 50%)

root.play_icon = play_icon
root.stop_icon = stop_icon
root.exit_icon = exit_icon
root.volume_down_icon = volume_down_icon
root.volume_up_icon = volume_up_icon
root.mute_icon = mute_icon

# === Wetter-Icons (PNG) laden ===
icon_size = 64
weather_icon_images = {}

icon_folder = os.path.join(BASE_DIR, "img", "weather_icons")

for filename in os.listdir(icon_folder):
    if filename.endswith(".png"):
        code = filename.replace(".png", "")
        path = os.path.join(icon_folder, filename)

        img = Image.open(path).resize((icon_size, icon_size), Image.LANCZOS)
        weather_icon_images[code] = ImageTk.PhotoImage(img)

# Header
header = tk.Frame(root, bg="#222222", height=40)
header.pack(fill="x")
title_label = tk.Label(header, text="Webradio", font=("Arial", 16, "bold"),
                       bg="#222222", fg="white")
title_label.pack(side="left", padx=10)

# Variable für Datum/Uhrzeit
datetime_var = tk.StringVar()
datetime_var.set("")  # wird gleich aktualisiert

# Label für Datum/Uhrzeit (oben rechts)
datetime_label = tk.Label(header, textvariable=datetime_var,
                          font=("Arial", 12),  # normale Schrift für Datum/Uhrzeit
                          bg="#222222", fg="#bbbbbb")
datetime_label.pack(side="right", padx=10)
# endregion


# region Wetter

# ----- Wetteranzeige als "Langloch" -----
langloch_height = 80
radius = langloch_height // 2

extra_width = 20
padding = 30

initial_width = 400  # bewusst etwas größer wählen

weather_canvas = tk.Canvas(
    root,
    width=initial_width,
    height=langloch_height,
    bg="#222222",
    highlightthickness=0
)
weather_canvas.pack(pady=15)

# Langloch-Hintergrund speichern
weather_bg_rect = weather_canvas.create_rectangle(
    radius, 0,
    initial_width - radius, langloch_height,
    fill="#333333",
    outline=""
)

weather_bg_left = weather_canvas.create_oval(
    0, 0,
    radius * 2, langloch_height,
    fill="#333333",
    outline=""
)

weather_bg_right = weather_canvas.create_oval(
    initial_width - radius * 2, 0,
    initial_width, langloch_height,
    fill="#333333",
    outline=""
)

# Innerer Frame
weather_inner = tk.Frame(weather_canvas, bg="#333333")

weather_window = weather_canvas.create_window(
    initial_width // 2,
    langloch_height // 2,
    window=weather_inner
)

# ---- Icon links ----
weather_icon_label = tk.Label(weather_inner, bg="#333333")
weather_icon_label.pack(side="left", padx=(10,15), pady=5)

# ---- Textbereich ----
weather_text_frame = tk.Frame(weather_inner, bg="#333333")
weather_text_frame.pack(side="left")

# Obere Zeile
top_row_frame = tk.Frame(weather_text_frame, bg="#333333")
top_row_frame.pack(anchor="w")

weather_temp_var = tk.StringVar()
weather_temp_label = tk.Label(
    top_row_frame,
    textvariable=weather_temp_var,
    font=("Arial", 24, "bold"),
    bg="#333333",
    fg="white"
)
weather_temp_label.pack(side="left")

# Neues Label für Wind mit Icon
weather_wind_label = tk.Label(top_row_frame, bg="#333333")
weather_wind_label.pack(side="left", padx=(15,0))
bft_label = tk.Label(top_row_frame, text="0 bft",  # Platzhalter
                     font=("Arial", 24, "bold"), bg="#333333", fg="white")
bft_label.pack(side="left", padx=(5,0))

# Wind-Warnsymbol (startet leer)
wind_warning_label = tk.Label(top_row_frame, bg="#333333")
wind_warning_label.pack(side="left", padx=(10,0))

# Untere Zeile
bottom_row_frame = tk.Frame(weather_text_frame, bg="#333333")
bottom_row_frame.pack(anchor="w")

weather_desc_var = tk.StringVar()
weather_desc_label = tk.Label(
    bottom_row_frame,
    textvariable=weather_desc_var,
    font=("Arial", 12),
    bg="#333333",
    fg="#bbbbbb"
)
weather_desc_label.pack(side="left")

# --- Neuer Frame für Pressure & Humidity ---
weather_details_frame = tk.Frame(bottom_row_frame, bg="#333333")
weather_details_frame.pack(side="left", padx=(15,0))

# Pressure
pressure_label_icon = tk.Label(weather_details_frame, image=pressure_icon_img, bg="#333333")
pressure_label_icon.pack(side="left")

pressure_label_text = tk.Label(weather_details_frame, text="0 hPa",
                               font=("Arial", 12), bg="#333333", fg="#bbbbbb")
pressure_label_text.pack(side="left", padx=(3,10))

# Humidity
humidity_label_icon = tk.Label(weather_details_frame, image=humidity_icon_img, bg="#333333")
humidity_label_icon.pack(side="left")

humidity_label_text = tk.Label(weather_details_frame, text="0%",
                               font=("Arial", 12), bg="#333333", fg="#bbbbbb")
humidity_label_text.pack(side="left", padx=(3,0))
# endregion


# region Senderauswahl

# Sender-Buttons + Scroll-Pfeile
button_frame = tk.Frame(root, bg="#222")
button_frame.pack(pady=5)

button_frame.grid_columnconfigure(0, weight=0)
button_frame.grid_columnconfigure(1, weight=1)
button_frame.grid_columnconfigure(2, weight=1)
button_frame.grid_columnconfigure(3, weight=1)
button_frame.grid_columnconfigure(4, weight=1)
button_frame.grid_columnconfigure(5, weight=0)

# Senderliste automatisch aus Dictionary erzeugen
stations_list = list(stations.keys())
# print("Stations list:", stations_list)
VISIBLE_STATIONS = 4
station_start_index = 0
buttons = {}

# Scroll-Funktionen
def scroll_left():
    global station_start_index
    if station_start_index > 0:
        station_start_index -= 1
        update_station_buttons()

def scroll_right():
    global station_start_index
    if station_start_index + VISIBLE_STATIONS < len(stations_list):
        station_start_index += 1
        update_station_buttons()

# Sender-Buttons erstellen
for name in stations_list:
    info = stations[name]
    logo_path = os.path.join(BASE_DIR, info["logo"])

    if os.path.exists(logo_path):
        img = Image.open(logo_path).resize((150,150), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    else:
        photo = None

    btn = tk.Button(
        button_frame,
        image=photo,
        command=lambda n=name: play_station(n, stations[n]["url"]),
        # bg="#222",
        bg="#e3e3e3",
        activebackground="#222",
        bd=0
    )
    btn.image = photo
    buttons[name] = btn

# Scroll-Pfeile erstellen
left_arrow_img = load_icon("arrow_left.png", size=(40,140))
right_arrow_img = load_icon("arrow_right.png", size=(40,140))

left_arrow_btn = tk.Button(
    button_frame,
    image=left_arrow_img,
    bg="#222",
    bd=0,
    highlightthickness=1,          # Rahmendicke
    highlightbackground="#444",    # unauffälliges Grau
    activebackground="#222",
    command=scroll_left)

right_arrow_btn = tk.Button(
    button_frame,image=right_arrow_img,
    bg="#222",
    bd=0,
    highlightthickness=1,          # Rahmendicke
    highlightbackground="#444",    # unauffälliges Grau
    activebackground="#222",
    command=scroll_right)

# Layout-Funktion
def update_station_buttons():
    # Alles entfernen
    for btn in buttons.values():
        btn.grid_forget()
    left_arrow_btn.grid_forget()
    right_arrow_btn.grid_forget()

    # Sichtbare Sender bestimmen
    visible = stations_list[station_start_index:station_start_index + VISIBLE_STATIONS]

    # Sender anzeigen
    for col, name in enumerate(visible):
        buttons[name].grid(row=0, column=col+1, padx=5, pady=10)

    # Pfeile anzeigen falls nötig
    if station_start_index > 0:
        left_arrow_btn.grid(row=0, column=0, padx=(5,0))

    if station_start_index + VISIBLE_STATIONS < len(stations_list):
        right_arrow_btn.grid(row=0, column=VISIBLE_STATIONS+1, padx=(0,5))

# Initial anzeigen
root.after(100, update_station_buttons)

# Letzten Sender hervorheben
if last_station_name and last_station_name in buttons:
    highlight_active_station(last_station_name)

# Now Playing Anzeige
now_playing_var = tk.StringVar()
now_playing_var.set("Jetzt läuft:")

now_playing_label = tk.Label(
    root,
    textvariable=now_playing_var,
    font=("Arial", 12),
    bg="#222",
    fg="#bbbbbb"
)
now_playing_label.pack(pady=5)
# endregion


# region Playerfunktionalität

# Player-Steuerung
control_canvas = tk.Canvas(
    root,
    width=800,
    height=170,
    bg="#222222",
    highlightthickness=0
)
control_canvas.pack(pady=0)

# Radius für Haupt-Buttons und Side-Buttons
BUTTON_MAIN = 30
BUTTON_SIDE = 22

# Y-Position aller Buttons
BUTTON_Y = 60

# Funktion zum Erstellen von Kreis-Buttons mit Bild
def create_circle_button(canvas, x, y, r, image, command):
    circle = canvas.create_oval(x-r, y-r, x+r, y+r, fill="#3a3a3a", outline="")
    img_item = canvas.create_image(x, y, image=image)
    
    # Klick
    canvas.tag_bind(circle, "<Button-1>", lambda e: command())
    canvas.tag_bind(img_item, "<Button-1>", lambda e: command())
    
    # Hover
    def on_enter(e):
        canvas.itemconfig(circle, fill="#5a5a5a")
    def on_leave(e):
        update_control_highlight()

    canvas.tag_bind(circle, "<Enter>", lambda e: None)
    canvas.tag_bind(circle, "<Leave>", lambda e: update_control_highlight())
    
    return circle


# Buttons erzeugen

# Stop / Play / Exit
stop_circle = create_circle_button(control_canvas, 90, BUTTON_Y, BUTTON_MAIN, root.stop_icon, stop_station)
play_circle = create_circle_button(control_canvas, 170, BUTTON_Y, BUTTON_MAIN, root.play_icon, play_last_station)
exit_circle = create_circle_button(control_canvas, 250, BUTTON_Y, BUTTON_MAIN, root.exit_icon, exit_app)

# Mute
mute_circle = create_circle_button(control_canvas, 380, BUTTON_Y, BUTTON_SIDE, root.mute_icon, toggle_mute)

# Volume Down / Up
vol_down_circle = create_circle_button(control_canvas, 450, BUTTON_Y, BUTTON_SIDE, root.volume_down_icon, vol_down)
vol_up_circle   = create_circle_button(control_canvas, 650, BUTTON_Y, BUTTON_SIDE, root.volume_up_icon, vol_up)

# Volume-Bar Slot
volume_slot_x = 550
volume_slot_y = BUTTON_Y
volume_slot_width = 140
volume_slot_height = 24
bar_radius = volume_slot_height / 2  # volle Höhe → Kapsel

# Hintergrund Langloch
control_canvas.create_oval(
    volume_slot_x - volume_slot_width/2,
    volume_slot_y - bar_radius,
    volume_slot_x - volume_slot_width/2 + bar_radius*2,
    volume_slot_y + bar_radius,
    fill="#3a3a3a", outline=""
)
control_canvas.create_oval(
    volume_slot_x + volume_slot_width/2 - bar_radius*2,
    volume_slot_y - bar_radius,
    volume_slot_x + volume_slot_width/2,
    volume_slot_y + bar_radius,
    fill="#3a3a3a", outline=""
)
control_canvas.create_rectangle(
    volume_slot_x - volume_slot_width/2 + bar_radius,
    volume_slot_y - bar_radius,
    volume_slot_x + volume_slot_width/2 - bar_radius,
    volume_slot_y + bar_radius,
    fill="#3a3a3a", outline=""
)

# Progressbar
volume_var = tk.IntVar(value=current_volume)
volume_bar = ttk.Progressbar(
    control_canvas,
    orient="horizontal",
    length=volume_slot_width - 16,
    mode="determinate",
    maximum=100,
    variable=volume_var
)
control_canvas.create_window(volume_slot_x, volume_slot_y, window=volume_bar)
update_volume_style()

# Label für die Lautstärke direkt unterhalb der Bar
label_width = 30
label_height = 20
label_radius = 6
label_padding_top = 2

# Hintergrund Kapsel
x0 = volume_slot_x - label_width/2
y0 = volume_slot_y + volume_slot_height/2 + label_padding_top
x1 = volume_slot_x + label_width/2
y1 = y0 + label_height

control_canvas.create_oval(x0, y0, x0 + label_radius*2, y1, fill="#3a3a3a", outline="")
control_canvas.create_oval(x1 - label_radius*2, y0, x1, y1, fill="#3a3a3a", outline="")
control_canvas.create_rectangle(x0 + label_radius, y0, x1 - label_radius, y1, fill="#3a3a3a", outline="")

volume_label = tk.Label(
    control_canvas,  # jetzt im gleichen Canvas wie die Bar
    textvariable=volume_var,
    font=("Arial", 11),
    bg="#3a3a3a",
    fg="white",
)
control_canvas.create_window(
    volume_slot_x, 
    y0 + label_height/2,
    window=volume_label
)

# Funktion zum Setzen der Lautstärke
def set_volume(self, vol):
    self.send({"command": ["set_property", "volume", vol]})
    volume_var.set(vol)  # Zahl aktualisieren

# Direkt initial Highlight aktualisieren
update_control_highlight()

last = load_last_station()
if last:
    last_station_name = last
    play_last_station()           # mpv-Stream starten
    highlight_active_station(last_station_name)  # Button grün markieren
    update_control_highlight()    # Play-Button grün setzen
else:
    update_control_highlight()    # Stop grün, falls keine Station
# endregion


# sofort starten
update_datetime()
update_weather()
update_now_playing()

root.mainloop()
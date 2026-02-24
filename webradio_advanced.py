import tkinter as tk
import tkinter.ttk as ttk
import subprocess
import sys
import datetime
import time
import os
import json
import socket
import requests
import io
from PIL import Image, ImageTk
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----- Radiosender -----
stations = {
    "NDR 2 SH": {
        "url": "https://icecast.ndr.de/ndr/ndr2/schleswigholstein/mp3/128/stream.mp3",
        "logo": "img/ndr2schleswigholstein.png"
    },
    "Beats Radio": {
        "url": "http://live.streams.klassikradio.de/beats-radio/stream/mp3",
        "logo": "img/beatsradio.png"
    },
    "R.SH": {
        "url": "https://streams.rsh.de/rsh-live/mp3-128/streams.rsh.de/",
        "logo": "img/rsh.png"
    },
    "Ibiza Global": {
        "url": "http://ibizaglobalradio.streaming-pro.com:8024/listen.pls?sid=1",
        "logo": "img/ibizaglobalradio.png"
    }
}

# Absoluter Pfad zur .env-Datei relativ zum Skript
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# API-Key aus Umgebungsvariable
WEATHER_API_KEY = os.getenv("OWM_KEY")

# Test-Ausgabe
print("API Key:", WEATHER_API_KEY)

player_process = None
current_volume = 50
mpv_socket_path = "/tmp/mpv-socket"
last_station_file = "/home/pi/webradio/last_station.txt"
last_station_name = None
active_control = None
# WEATHER_API_KEY = os.getenv("OWM_KEY")
WEATHER_LAT = "54.80797555"
WEATHER_LON = "9.52438474"
WEATHER_EXCL = "minutely,hourly,daily,alerts"
muted = False
last_volume_before_mute = current_volume

load_dotenv()

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

mpv = MPV(mpv_socket_path, lambda: player_process)

# ----- Funktionen -----
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
    datetime_text = f"📅 {wochentag_de}, {jetzt.day:02d}.{jetzt.month:02d}.{jetzt.year}  ⏰ {jetzt.hour:02d}:{jetzt.minute:02d} Uhr"
    
    # Variable aktualisieren
    datetime_var.set(datetime_text)
    
    # Alle 10 Sekunden erneut aufrufen
    root.after(10000, update_datetime)

def update_weather():
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

        temp = round(data["current"]["temp"])
        desc = data["current"]["weather"][0]["description"]
        icon_code = data["current"]["weather"][0]["icon"]

        # ---- ICON LADEN ----
        icon_url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"

        icon_response = requests.get(icon_url, timeout=5)
        img_data = icon_response.content

        img = Image.open(io.BytesIO(img_data))
        photo = ImageTk.PhotoImage(img)

        weather_icon_label.config(image=photo)
        weather_icon_label.image = photo

        # ---- TEXT ----
        weather_temp_var.set(f"{temp}°C")
        weather_desc_var.set(desc.capitalize())

    except Exception:
        weather_temp_var.set("Wetterdaten Fehler")

    root.after(600000, update_weather)  # alle 10 Minuten

def play_station(name, url):
    global player_process, last_station_name
    last_station_name = name
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

def highlight_active_station(active_name):
    for name, btn in buttons.items():
        if name == active_name:
            btn.config(highlightbackground="#22aa22", highlightthickness=5)  # #22aa22=grün #FFC200=gelb
        else:
            btn.config(highlightbackground="#222", highlightthickness=1)       # neutral

def update_now_playing():
    """Liest den aktuellen ICY Titel aus mpv."""
    
    if player_process is None or player_process.poll() is not None:
        now_playing_var.set("Now Playing: ---")
        root.after(2000, update_now_playing)
        return

    if not os.path.exists(mpv_socket_path):
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

            if title:
                now_playing_var.set(f"Es läuft gerade: 🎵 {title}")
            else:
                now_playing_var.set("Es läuft gerade: ---")

    except Exception:
        pass

    root.after(2000, update_now_playing)  # alle 2 Sekunden

def highlight_control(button_name):
    global active_control
    active_control = button_name

    # Rahmen setzen
    if active_control == "play":
        play_btn.config(highlightbackground="#22aa22", highlightthickness=5) # #22aa22=grün #FFC200=gelb
        stop_btn.config(highlightbackground="#222", highlightthickness=1)
    elif active_control == "stop":
        stop_btn.config(highlightbackground="#22aa22", highlightthickness=5)
        play_btn.config(highlightbackground="#222", highlightthickness=1)
    else:
        play_btn.config(highlightbackground="#222", highlightthickness=1)
        stop_btn.config(highlightbackground="#222", highlightthickness=1)

def play_last_station():
    if last_station_name and last_station_name in stations:
        play_station(last_station_name, stations[last_station_name]["url"])
        highlight_control("play")

def stop_station():
    global player_process
    highlight_control("stop")

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
    update_mute_button()

def update_mute_button():
    if muted:
        mute_btn.config(
            bg="#cc3333",          # rot = gemutet
            relief="solid",
            bd=2
        )
    else:
        mute_btn.config(
            bg="#f0f0f0",
            relief="flat",
            bd=0
        )

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

# ----- GUI -----
root = tk.Tk()
style = ttk.Style()
style.theme_use("default")

# Standardhöhe (Fallback)
style.configure(
    "TProgressbar",
    thickness=18
)

# Leise
style.configure(
    "Vol.Low.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#666",
    lightcolor="#666",
    darkcolor="#666",
    bordercolor="#000",
    thickness=18
)

# Mittel
style.configure(
    "Vol.Mid.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#22aa22",
    lightcolor="#22aa22",
    darkcolor="#22aa22",
    bordercolor="#000",
    thickness=18
)

# Laut
style.configure(
    "Vol.High.Horizontal.TProgressbar",
    troughcolor="#222",
    background="#cc3333",
    lightcolor="#cc3333",
    darkcolor="#cc3333",
    bordercolor="#000",
    thickness=18
)

root.attributes("-fullscreen", True)
root.configure(bg="#222")

play_icon = load_icon("play.png")
stop_icon = load_icon("stop.png")
exit_icon = load_icon("exit.png")
volume_down_icon = load_icon("volume_down.png", (32, 32))
volume_up_icon = load_icon("volume_up.png", (32, 32))
mute_icon = load_icon("mute.png", (32, 32))

root.play_icon = play_icon
root.stop_icon = stop_icon
root.exit_icon = exit_icon
root.volume_down_icon = volume_down_icon
root.volume_up_icon = volume_up_icon
root.mute_icon = mute_icon

# Header
header = tk.Frame(root, bg="#111", height=40)
header.pack(fill="x")
title_label = tk.Label(header, text="Webradio", font=("Arial", 16, "bold"),
                       bg="#111", fg="white")
title_label.pack(side="left", padx=10)

# Variable für Datum/Uhrzeit
datetime_var = tk.StringVar()
datetime_var.set("")  # wird gleich aktualisiert

# Label für Datum/Uhrzeit (oben rechts)
datetime_label = tk.Label(header, textvariable=datetime_var,
                          font=("Arial", 12),  # normale Schrift für Datum/Uhrzeit
                          bg="#111", fg="#bbbbbb")
datetime_label.pack(side="right", padx=10)

last = load_last_station()
if last:
    last_station_name = last

# Label für Wetter
weather_frame = tk.Frame(root, bg="#222")
weather_frame.pack(pady=10)

weather_icon_label = tk.Label(weather_frame, bg="#222")
weather_icon_label.pack(side="left", padx=15)

weather_text_frame = tk.Frame(weather_frame, bg="#222")
weather_text_frame.pack(side="left")

weather_temp_var = tk.StringVar()
weather_temp_var.set("--°C")

weather_desc_var = tk.StringVar()
weather_desc_var.set("")

weather_temp_label = tk.Label(
    weather_text_frame,
    textvariable=weather_temp_var,
    font=("Arial", 26, "bold"),   # <<< GROSS
    bg="#222",
    fg="white"
)
weather_temp_label.pack(anchor="w")

weather_desc_label = tk.Label(
    weather_text_frame,
    textvariable=weather_desc_var,
    font=("Arial", 11),           # <<< KLEINER
    bg="#222",
    fg="#bbbbbb"
)
weather_desc_label.pack(anchor="w")

# Sender-Buttons
button_frame = tk.Frame(root, bg="#222")
button_frame.pack(pady=5)

buttons = {}
col = 0

for name, info in stations.items():

    logo_path = os.path.join(BASE_DIR, info["logo"])

    if os.path.exists(logo_path):
        img = Image.open(logo_path)
        img = img.resize((150, 150))   # <<< PERFEKTE Größe
        photo = ImageTk.PhotoImage(img)
    else:
        photo = None


    btn = tk.Button(
        button_frame,
        image=photo,
        command=lambda n=name, u=info["url"]: play_station(n, u),
        bg="#222",
        activebackground="#222",
        bd=0
    )
    
    btn.image = photo
    btn.grid(row=0, column=col, padx=15, pady=10)
    col += 1

    buttons[name] = btn

if last_station_name:
    highlight_active_station(last_station_name)

# Now Playing Anzeige
now_playing_var = tk.StringVar()
now_playing_var.set("Es läuft gerade: ---")

now_playing_label = tk.Label(
    root,
    textvariable=now_playing_var,
    font=("Arial", 12),
    bg="#222",
    fg="#bbbbbb"
)
now_playing_label.pack(pady=5)

# STOP + EXIT
control_frame = tk.Frame(root, bg="#222")
control_frame.pack(pady=10)

stop_btn = tk.Button(
    control_frame,
    image=root.stop_icon,
    command=stop_station,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
)
stop_btn.pack(side="left", padx=15)

play_btn = tk.Button(
    control_frame,
    image=root.play_icon,
    command=play_last_station,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
)
play_btn.pack(side="left", padx=15)

exit_btn = tk.Button(
    control_frame,
    image=root.exit_icon,
    command=exit_app,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
)
exit_btn.pack(side="left", padx=15)

# ----- Abstand nach Exit -----
spacer = tk.Frame(control_frame, width=40, bg="#222")
spacer.pack(side="left")

# Lautstärke
volume_var = tk.IntVar(value=current_volume)

mute_btn = tk.Button(
    control_frame,
    image=root.mute_icon,
    command=toggle_mute,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
)
mute_btn.pack(side="left", padx=(25))

vol_down_btn = tk.Button(
    control_frame,
    image=root.volume_down_icon,
    command=vol_down,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
    )
vol_down_btn.pack(side="left", padx=5)

volume_bar = ttk.Progressbar(
    control_frame,
    orient="horizontal",
    length=180,          # Breite des Balkens
    mode="determinate",
    maximum=100,
    variable=volume_var
)
volume_bar.pack(side="left", padx=5)
update_volume_style()

vol_up_btn = tk.Button(
    control_frame,
    image=root.volume_up_icon,
    command=vol_up,
    bd=0,
    bg="#f0f0f0",
    activebackground="#a0a0a0"
    )
vol_up_btn.pack(side="left", padx=5)

# ----- Start zuletzt gespielter Sender und Button-Highlight -----
if last_station_name:
    highlight_active_station(last_station_name)  # grüner Rahmen um Sender
    highlight_control("play")                    # Play-Button grün umrahmen
    play_last_station()                           # Stream starten
else:
    highlight_control("stop")                    # Stop-Button grün umrahmen, falls keine letzte Station

# sofort starten
update_datetime()
update_weather()
update_now_playing()

root.mainloop()
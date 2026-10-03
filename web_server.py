import os
import socket
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import settings
import work_fuctions

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

ai_instance = None
server_instance = None

class QueryModel(BaseModel):
    text: str

class CommandModel(BaseModel):
    cmd: str   # полная команда, начинающаяся с '/'

class LocationModel(BaseModel):
    lat: float
    lng: float
    accuracy: float | None = None
    source: str = "web"

class RouteModel(BaseModel):
    destination: str   # описание цели маршрута (адрес/фраза)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@app.get("/")
def index():
    html_path = Path("index.html")
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Файл index.html не найден")
    return FileResponse(html_path)

@app.post("/api/ask")
def ask_ai(data: QueryModel):
    global ai_instance
    if not ai_instance:
        raise HTTPException(status_code=500, detail="Экземпляр AI не инициализирован")

    ai_instance.response_ready_event.clear()
    ai_instance.user_prompt = data.text

    is_ready = ai_instance.response_ready_event.wait(timeout=60)
    if not is_ready:
        raise HTTPException(status_code=504, detail="Превышено время ожидания ответа ИИ")

    return {
        "status": "ok",
        "response": ai_instance.format_response(ai_instance.response),
        "play_audio": getattr(ai_instance, 'ai_speak', False)
    }

@app.post("/api/command")
def execute_command(data: CommandModel):
    global ai_instance
    if not ai_instance:
        raise HTTPException(status_code=500, detail="AI не инициализирован")
    try:
        result = ai_instance.process_command(data.cmd)
        return {"status": "ok", "output": result}
    except Exception as e:
        return {"status": "error", "output": str(e)}

@app.post("/api/voice")
async def ask_ai_voice(file: UploadFile = File(...)):
    global ai_instance
    if not ai_instance:
        raise HTTPException(status_code=500, detail="Экземпляр AI не инициализирован")

    temp_raw = "temp_mobile_raw"
    target_wav = settings.PATHS.get("temp_wav_file", "temp.wav")

    with open(temp_raw, "wb") as f:
        f.write(await file.read())

    subprocess.run([
        "ffmpeg", "-y", "-i", temp_raw,
        "-ar", "16000", "-ac", "1", target_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(temp_raw):
        os.remove(temp_raw)

    ai_instance.response_ready_event.clear()
    ai_instance.pending_voice = True

    is_ready = ai_instance.response_ready_event.wait(timeout=60)
    if not is_ready:
        raise HTTPException(status_code=504, detail="Превышено время ожидания ответа ИИ")

    # Проверка стоп-слова
    if getattr(ai_instance, 'stop_audio_triggered', False):
        ai_instance.stop_audio_triggered = False
        return {
            "status": "stop_audio",
            "user_text": "",
            "response": "",
            "play_audio": False
        }

    # Игнорирование (чужой голос или нет триггера)
    if getattr(ai_instance, 'ignore_response', False):
        ai_instance.ignore_response = False
        return {
            "status": "ignored",
            "user_text": "",
            "response": "",
            "play_audio": False
        }

    return {
        "status": "ok",
        "user_text": ai_instance.user_prompt or "Голосовой запрос",
        "response": ai_instance.format_response(ai_instance.response),
        "play_audio": getattr(ai_instance, 'ai_speak', False) or getattr(ai_instance, 'is_voice_success', False)
    }

@app.get("/api/audio")
def get_audio():
    return FileResponse(settings.PATHS["response_path"], media_type="audio/wav")

@app.get("/api/alerts")
def get_alerts():
    # Отдаем уведомления веб-клиенту и сразу очищаем очередь
    if hasattr(work_fuctions, "web_alerts") and len(work_fuctions.web_alerts) > 0:
        alerts_to_send = work_fuctions.web_alerts.copy()
        work_fuctions.web_alerts.clear()
        return {"alerts": alerts_to_send}
    return {"alerts": []}

@app.get("/api/alert_audio")
def get_alert_audio():
    # Отдаем сгенерированный аудиофайл таймера
    file_path = "/tmp/timer_alert.wav"
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/wav")
    raise HTTPException(status_code=404, detail="Audio not found")

@app.post("/api/location")
def post_location(data: LocationModel):
    """Принять текущие координаты клиента (телефон/браузер)."""
    result = work_fuctions.update_location(data.lat, data.lng, data.accuracy, data.source)
    return {"status": "ok", "message": result}

@app.get("/api/location")
def get_location():
    """Вернуть текущую позицию клиента."""
    return work_fuctions.get_location()

@app.get("/api/location/history")
def get_location_history():
    """Вернуть историю перемещений клиента."""
    return {"history": work_fuctions.location_history}

@app.get("/api/location/request")
def location_request_status():
    """Есть ли активный запрос координат со стороны ИИ."""
    return {"pending": getattr(work_fuctions, "location_request_pending", False)}

@app.post("/api/location/request/resolve")
def location_request_resolve():
    """Сбросить запрос координат (клиент прислал позицию)."""
    work_fuctions.location_request_pending = False
    return {"status": "ok"}

@app.get("/api/navigator/status")
def navigator_status():
    """Состояние навигатора: активен ли, маршрут, текущий маневр."""
    status = work_fuctions.navigation_status()
    status["location"] = work_fuctions.get_location()
    status["ready"] = work_fuctions.location_data.get("lat") is not None
    return status

@app.post("/api/navigator/start")
def navigator_start(data: RouteModel):
    """Запустить голосовую навигацию до цели."""
    result = work_fuctions.start_navigation(data.destination)
    return {"status": "ok", "data": result}

@app.post("/api/navigator/stop")
def navigator_stop():
    """Остановить голосовую навигацию."""
    result = work_fuctions.stop_navigation()
    return {"status": "ok", "data": result}

@app.get("/api/state")
def get_ai_state():
    """Текущее состояние AI для подсветки 3D-ядра.
    idle | listening | thinking | speaking | command | error"""
    if not ai_instance:
        return {"state": "idle", "provider": "", "model": ""}
    return {
        "state": getattr(ai_instance, "ai_state", "idle"),
        "provider": getattr(ai_instance, "provider", ""),
        "model": (getattr(ai_instance, "model", "") or getattr(ai_instance, "zen_model", "")),
    }

def stop_server():
    global server_instance
    if server_instance:
        server_instance.should_exit = True

def start_server_in_thread(ai_obj, port=1337):
    global ai_instance, server_instance
    ai_instance = ai_obj
    ip = get_local_ip()

    for i in range(20):
        print(f" http://{ip}:{port}")

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
    server_instance = uvicorn.Server(config)
    server_instance.run()
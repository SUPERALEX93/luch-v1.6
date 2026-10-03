# ЛУЧ v1.6

Голосовой ассистент для Arch Linux: распознавание речи, синтез голоса, локальные и
облачные LLM, управление компьютером, компьютерное зрение и веб-интерфейс.

Версия 1.6 — про компьютерное зрение: ассистент получает кадры с экрана или камеры
и описывает, что на них происходит. Android-клиента в этой версии ещё нет
(он появился в 1.7).

---

## Что умеет

| Возможность | Модуль |
|---|---|
| Распознавание речи (faster-whisper локально или Google) | `main.py` |
| Голосовой пропуск — ассистент реагирует только на ваш тембр | `main.py` (speechbrain ECAPA) |
| Синтез речи (Silero TTS, русские голоса) | `main.py` |
| Локальные модели через Ollama | `main.py` |
| Облачные модели: OpenCode Zen, любой OpenAI-совместимый провайдер | `main.py` |
| Компьютерное зрение (YOLO, ultralytics) | `work_fuctions.py` |
| Управление ПК: терминал, блокировка, таймеры, поиск | `work_fuctions.py` |
| Навигация, геокодирование, поиск мест рядом | `work_fuctions.py` |
| Веб-интерфейс и REST API | `web_server.py`, `index.html` |
| GUI-монитор | `gui_launcher.py` |

---

## Структура

```
v1.6/
├── main.py                 ядро: голосовой цикл, STT/TTS, работа с LLM
├── web_server.py           FastAPI: REST API, статика
├── work_fuctions.py        инструменты ассистента, зрение (YOLO)
├── settings.py             загрузка/сохранение settings.json
├── gui_launcher.py         GUI-монитор и запуск ядра (PySide6)
└── index.html              веб-интерфейс
```

Модели зрения (`yolov8m.pt`, `yolo11x.pt`, `yoloe-26s-seg-pf.pt`) и веса распознавания
речи лежат рядом, но в git не публикуются — их нужно скачивать отдельно.

---

## Установка

```bash
python -m venv ai_env
source ai_env/bin/activate

# torch/torchaudio для CUDA — из отдельного индекса
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130

pip install faster-whisper speechbrain sounddevice torch torchaudio \
    silero-tts ollama ultralytics rich PySide6 fastapi uvicorn httpx
```

---

## Запуск

```bash
python main.py        # ядро + веб-интерфейс
python gui_launcher.py  # GUI-монитор (запускает ядро сам)
```

При первом запуске ассистент попросит произнести длинную фразу — эталон вашего
голоса для голосового пропуска.

Веб-интерфейс: `http://<ip>:1337`.

---

## Безопасность

> `settings.json` и `memory.txt` содержат ключи в открытом виде. Не публикуйте их.
> Веб-API в этой версии не защищён токеном — не выставляйте порт наружу.

---

## Что дальше

- **1.7** — Android-клиент: управление телефоном голосом, геолокация, уведомления.
- **1.8** — обязательная аутентификация веб-API, полный аудит кода.

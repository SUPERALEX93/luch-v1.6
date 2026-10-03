import os
import warnings
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
os.environ["LOGURU_LEVEL"] = "ERROR"
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")
import logging
logging.getLogger().setLevel(logging.ERROR)
for name in ["torch", "torchaudio", "urllib3", "requests", "speechbrain", "silero_tts"]:
    logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger(name).propagate = False
import torch
import importlib
import ollama
import json
import time
import subprocess
from art import *
from colorama import Fore, Back, Style
import colorama
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED, SIMPLE, DOUBLE
from rich.theme import Theme
import threading
from pathlib import Path
import requests
import speech_recognition as sr
from faster_whisper import WhisperModel,available_models
from silero_tts.silero_tts import SileroTTS
from datetime import datetime
import pygame
import numpy as np
from python_speech_features import mfcc
from scipy.spatial.distance import cosine
import scipy.io.wavfile as wav
import torchaudio.transforms as T
from colorama import Fore, Style, init
import torch
from ollama import chat
import settings
import work_fuctions
import web_server

colorama.init()
pygame.init()
pygame.mixer.init()

import torchaudio
if not hasattr(torchaudio, 'list_audio_backends'):
    torchaudio.list_audio_backends = lambda: ['soundfile']

from speechbrain.inference.speaker import SpeakerRecognition
from speechbrain.utils.fetching import LocalStrategy

class AIconsole:
    def __init__(self):
        self.stop_audio_triggered = False
        self.ignore_response = False
        self.response_ready_event = threading.Event()
        self.pending_voice = False
        self.memory_path = Path(settings.PATHS["memory_path"])
        self.memory = self.get_memory_from_file()
        self.sound = None
        self.ai_speak = False
        self.stop_speak_flags = settings.stop_speak_flags
        self.listen_while_ai_speak_flag = True
        self.type_work = "chat"
        self.ai_state = "idle"
        self.user_prompt = None
        self.ollama_url = "http://localhost:11434/api/"
        self.ollama_response = requests.get(self.ollama_url + "tags")
        self.ollama_data = self.ollama_response.json()
        self.ai_thread = threading.Thread(target=self.generate_ai_response, daemon=True)
        self.models_info = []
        self.default_settings = settings.default_settings
        self.global_context = "ГЛОБАЛЬНЫЙ КОНТЕКСТ: \n"
        self.second_context = ""
        self.response = ""
        self.font_for_welcome = "epic"
        self.font_for_menu = "small"
        self.console = Console(theme=Theme({
            "info": "cyan", "ok": "green", "err": "bold red",
            "user": "bold #89b4fa", "ai": "bold #f5c2e7", "cmd": "bold yellow",
        }))

        self.commands_ai = work_fuctions.commands_ai

        self.commands_ai_and_args = work_fuctions.commands_ai_and_args

        work_fuctions.tts_callback = self.play_timer_tts
        self._banner()
        self.second_system_prompt = ""
        self.model = settings.settings["model"]
        self.provider = settings.settings.get("provider", "ollama")
        self.zen_api_key = settings.settings.get("zen_api_key", "")
        self.zen_model = settings.settings.get("zen_model", "gpt-5.4-mini")
        self.zen_url = "https://opencode.ai/zen/v1/chat/completions"
        self.zen_models_url = "https://opencode.ai/zen/v1/models"
        self.whisper_model = settings.settings["whispermodel"]
        self.micro_index = settings.settings["micro_index"]
        self.tts_voice = settings.settings["tts_voice"]
        self.trigger_word = settings.settings["trigger_word"]
        self.speed_ai_speak = settings.settings["speed_ai_speak"]
        self.stt_mode = settings.settings["stt_mode"]
        self.profile_wav = settings.PATHS["voice_profile_path"]
        self.system_prompt = "Тебя зовут" + str(self.trigger_word) + """,Ты работаешь на Arch Linux. ВАЖНОЕ ПРАВИЛО: ОТВЕЧАЙ СРАЗУ И НАПРЯМУЮ. . ВЫДАВАЙ ТОЛЬКО ИТОГОВЫЙ ОТВЕТ!
Используй команды чтобы выполнить данное указание если ты считаешь что это нужно, либо ответь просто текстом.Вот как нужно отвечать:
1. Если нужно выполнить команду, то ответ ДОЛЖЕН НАЧИНАТЬСЯ С command(ОБЯЗАТЕЛЬНО) и быть в формате JSON,ОТВЕТ НЕ ДОЛЖЕН СОДЕРЖАТЬ НИЧЕГО ЛИШНЕГО КРОМЕ СЛОВА COMMAND В НАЧАЛЕ И САМОЙ КОМАНДЫ,к некоторым командам НЕ нужны аргументы(пример):
command {"command": "название_команды", "args": {"аргумент1": "значение1", "аргумент2": "значение2"}}. 
2. Если ты хочешь просто ответить текстом, то ответ должен быть просто текстом(если запрос user'a не элементарный то желательно используй web_search).
        """ + "Вот список доступных команд и их аргуметов: " + self.commands_ai_and_args + "\nЕСЛИ ТЫ ЧТО-ТО НЕ ПОМНИШЬ/НЕ ЗНАЕШЬ/НЕ РАСПОЛАГАЕШЬ ТАКОЙ ИНФОРМАЦИЕЙ ТО СНАЧАЛА ОБРАТИСЬ К ВНУТРЕННЕЙ ПАМЯТИ ЧЕРЕЗ ФУНКЦИИ.НЕ ОТВЕЧАЙ ПОЛЬЗОВАТЕЛЮ 'Я не знаю','У меня нет данных' И ТД."
        self.tts = SileroTTS(
            model_id='v4_ru',
            language='ru',
            speaker=self.tts_voice,
            device="cpu"
        )
        self.whisper_load_model = None
        if self.stt_mode == "whisper":
            self.whisper_load_model = WhisperModel(self.whisper_model, device="cuda", compute_type="float32") if self.whisper_model != "" else None

        self.user_commands = {
            "menu": [self.open_menu, "Opem the menu with available commands"],
            "exit": [work_fuctions.exit, "Exit the program"],
            "help": [self._show_help, "Show available commands"],
            "clear": [self.clear_console, "Clear the console"],
            "ai_model": [self.select_ai_model, "Select the AI model"],
            "whisper_model": [self.select_whisper_model, "Select the Whisper model"],
            "settings": [self.show_settings, "Show current settings"],
            "micro": [self.select_micro, "Select the microphone index"],
            "tts_voice": [self.select_tts_voice, "Select the TTS voice"],
            "trigger_word": [self.select_trigger_word, "Select the trigger word for AI"],
            "change_voice_profile": [self.make_voice_profile, "Change a voice profile"],
            "change_speed_ai_voice": [self.change_spped_ai_voice, "Change the speed of AI voice"],
            "clear_context": [self.clear_context, "Clear the context"],
            "change_stt_mode": [self.change_stt_mode, "Change stt mode"],
            "reload_libs": [self.reload_libs, "Reload settings and work_fuctions"],
            "restart_server": [self.restart_web_server, "Restart the web server"],
            "provider": [self.select_provider, "Switch AI provider: ollama | zen"],
            "zen_api": [self.set_zen_api_key, "Set OpenCode Zen API key"],
            "zen_model": [self.select_zen_model, "Select OpenCode Zen model"],
        }

        self.voice_verifier = SpeakerRecognition.from_hparams(
            source="microsoft/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec",
            local_strategy=LocalStrategy.COPY
        )
        self.profile_tensor = None

        recognizer = sr.Recognizer()

        with sr.Microphone(device_index=self.micro_index, sample_rate=48000, chunk_size=2048) as source:
            print(Fore.YELLOW + "MICROPHONE SETUP (BE SLIENT FOR 2 SECONDS)..." + Style.RESET_ALL)
            recognizer.adjust_for_ambient_noise(source, duration=2)

            if not os.path.exists(self.profile_wav):
                print(Fore.YELLOW + "=== THE VOICE STANDARD WAS NOT FOUND ===" + Style.RESET_ALL)
                print("SAY A LONG PHRASE (5 SECONDS) SO THAT THE AI REMEMBERS YOUR TIMBRE...")
                try:
                    print(Fore.CYAN + "THE RECORDIND HAS STERTED! SPEAK..." + Style.RESET_ALL)
                    enroll_audio = recognizer.record(source, duration=5)
                    with open(self.profile_wav, "wb") as f:
                        f.write(enroll_audio.get_wav_data())
                    print(Fore.GREEN + "YOUR REFERENCE VOICE IS SAVED!\n" + Style.RESET_ALL)
                except Exception as e:
                    print(Fore.RED + f"STANDARD RECORDING ERROR: {e}" + Style.RESET_ALL)
                    return

            self.load_profile_tensor()

    def _banner(self):
        """Премиум-приветственный баннер с названием ЛУЧ."""
        try:
            ascii_luch = str(text2art("LUCH", font="banner3"))
        except Exception:
            ascii_luch = "L U C H"
        versions = []
        from rich import box as _box
        lines = list(ascii_luch.split("\n"))
        # Градиент зелёный -> cyan -> magenta по строкам ASCII-арта
        colors = ["bold bright_green", "bold green", "bold cyan", "bold bright_cyan", "bold magenta"]
        logo = Text()
        for i, ln in enumerate(lines):
            c = colors[i % len(colors)]
            if ln.strip():
                logo.append(ln + "\n", style=c)
        logo.append("\n", style="bold")
        logo.append(" ✦ АССИСТЕНТ «ЛУЧ» ✦\n", style="bold #f5c2e7")
        self.console.print(Panel(
            logo,
            title="⚡ LUCH TERMINAL", title_align="left",
            border_style="#f5c2e7", box=DOUBLE, padding=(1, 2),
        ))
        cfg = f"[bold green]{getattr(self, 'trigger_word', None) or 'луч'}[/bold green]"
        prov = "OpenCode Zen" if getattr(self, 'provider', None) == "zen" else "Ollama"
        self._panel("⚙ БЫСТРЫЙ СТАРТ",
                    f"  [user]/help[/user] или [user]/menu[/user] — команды\n"
                    f"  [ok]Провайдер:[/ok] {prov}   [ok]Слово-триггер:[/ok] {cfg}\n"
                    f"  Скажи «{getattr(self, 'trigger_word', None) or 'луч'} + вопрос» голосом или введи текст",
                    style="info", box=SIMPLE)

    def _panel(self, title, text, style="ai", box=None, right=False):
        """Красивый вывод сообщения в Rich-панели."""
        box = box or ROUNDED
        t = Text.from_markup(str(text))
        self.console.print(Panel(
            t,
            title=title, title_align="right" if right else "left",
            border_style={"ai": "#f5c2e7", "cmd": "yellow", "user": "#89b4fa",
                          "info": "cyan", "err": "red", "ok": "green"}.get(style, style),
            box=box, padding=(0, 1),
        ))

    def _choice_menu(self, title, options, prompt="Введи номер выбора: "):
        """Красивое меню выбора из списка (Rich-панель). Возвращает выбранный элемент options[idx] или None."""
        lines = Text()
        for i, opt in enumerate(options, 1):
            lines.append(f"  {i}. ", style="bold #89b4fa")
            lines.append(f"{opt}\n", style="#cdd6f4")
        self.console.print(Panel(lines, title=f"⚙ {title}", border_style="cyan", box=ROUNDED, padding=(0, 1)))
        try:
            choice = input(Fore.GREEN + "  " + prompt + Style.RESET_ALL).strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1], int(choice)
        return None

    def _show_help(self):
        lines = Text("ДОСТУПНЫЕ КОМАНДЫ\n\n", style="bold cyan")
        for key, val in self.user_commands.items():
            lines.append(f"  /{key:<22}", style="bold #89b4fa")
            lines.append(f"{val[1]}\n", style="#6c7086")
        self.console.print(Panel(lines, title="ℹ СПРАВКА", border_style="cyan", box=ROUNDED, padding=(0, 1)))

    def restart_web_server(self):
        web_server.stop_server()
        time.sleep(0.5)
        importlib.reload(web_server)
        self.server_thread = threading.Thread(
            target=web_server.start_server_in_thread,
            args=(self,),
            daemon=True
        )
        self.server_thread.start()
    
    def reload_libs(self):
        try:
            importlib.reload(settings)
            importlib.reload(work_fuctions)
            self.stop_speak_flags = settings.stop_speak_flags
            self.commands_ai = work_fuctions.commands_ai
            self.commands_ai_and_args = work_fuctions.commands_ai_and_args
            self.model = settings.settings["model"]
            self.provider = settings.settings.get("provider", "ollama")
            self.zen_api_key = settings.settings.get("zen_api_key", "")
            self.zen_model = settings.settings.get("zen_model", "gpt-5.4-mini")
            self.zen_url = "https://opencode.ai/zen/v1/chat/completions"
            self.zen_models_url = "https://opencode.ai/zen/v1/models"
            self.whisper_model = settings.settings["whispermodel"]
            self.micro_index = settings.settings["micro_index"]
            self.tts_voice = settings.settings["tts_voice"]
            self.trigger_word = settings.settings["trigger_word"]
            self.speed_ai_speak = settings.settings["speed_ai_speak"]
            self.stt_mode = settings.settings["stt_mode"]
            self.profile_wav = settings.PATHS["voice_profile_path"]
        except Exception as e:
            print("error reload libs")

    def change_stt_mode(self):
        list_stt_modes = ["whisper", "google"]
        sel = self._choice_menu("РЕЖИМ РАСПОЗНАВАНИЯ РЕЧИ (STT)", list_stt_modes, "Выбери режим STT: ")
        if sel is None:
            return
        self.stt_mode = sel[0]
        settings.settings["stt_mode"] = self.stt_mode
        settings.save_settings()
        print(Fore.CYAN + "STT MODE CHANGED SUCCESSFULLY" + Style.RESET_ALL)

    def clear_context(self):
        self.global_context = ""
        print(Fore.CYAN + "CONTEXT CLEARED SUCCESSFULLY" + self.trigger_word + Style.RESET_ALL)

    def get_memory_from_file(self):
        try:
            if not self.memory_path.exists():
                self.memory_path.touch()
            with open(self.memory_path, "r", encoding="utf-8") as file:
                return file.read()
        except Exception as e:
            print("Error reading memory file: " + str(e))
            return "Error reading memory file: " + str(e)

    def change_spped_ai_voice(self):
        try:
            print(Fore.CYAN + "INPUT THE SPEED AI VOICE: >> " + Style.RESET_ALL, end="")
            self.speed_ai_speak = float(input())
            settings.settings["speed_ai_speak"] = self.speed_ai_speak
            settings.save_settings()
            print(Fore.GREEN + "SPEED AI VOICE SET TO " + str(self.speed_ai_speak) + " SUCCESSFULLY" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + "ERROR SETTING THE SPEED AI VOICE: " + str(e) + Style.RESET_ALL)

    def format_response(self, text):
        if not text.startswith("command "):
            text = text.replace('**', ' ').replace('```', ' ').replace('*',' ')
        else:
            orig = text
            try:
                text = text[8:-1] + "}"
                parsed = json.loads(text)
                type_command = parsed["command"]
                command = parsed["command"] + " " + str(parsed["args"])
                text = self.commands_ai[type_command]["icon"] + " " + command
            except Exception as e:
                return orig
        return text

    def make_voice_profile(self):
        recognizer = sr.Recognizer()
        with sr.Microphone(device_index=self.micro_index) as source:
            print(Fore.YELLOW + "MICROPHONE SETUP (BE SLIENT FOR 2 SECONDS)..." + Style.RESET_ALL)
            recognizer.adjust_for_ambient_noise(source, duration=2)

            print(Fore.YELLOW + "=== THE VOICE STANDARD WAS NOT FOUND ===" + Style.RESET_ALL)
            print("SAY A LONG PHRASE (5 SECONDS) SO THAT THE AI REMEMBERS YOUR TIMBRE...")
            try:
                print(Fore.CYAN + "THE RECORDIND HAS STERTED! SPEAK..." + Style.RESET_ALL)
                enroll_audio = recognizer.record(source, duration=5)
                with open(self.profile_wav, "wb") as f:
                    f.write(enroll_audio.get_wav_data())
                print(Fore.GREEN + "YOUR REFERENCE VOICE IS SAVED!\n" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"STANDARD RECORDING ERROR: {e}" + Style.RESET_ALL)
                return

            self.load_profile_tensor()

    def select_trigger_word(self):
        try:
            print(Fore.CYAN + "INPUT THE TRIGGER WORD: >> " + Style.RESET_ALL, end="")
            self.trigger_word = input()
            settings.settings["trigger_word"] = self.trigger_word
            settings.save_settings()
            print(Fore.CYAN + "TRIGGER WORD SET TO: " + self.trigger_word + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + "ERROR SETTING THE TRIGGER WORD: " + str(e) + Style.RESET_ALL)

    def get_audio_tensor(self, audio_data):
        raw_data = audio_data.get_raw_data()
        audio_np = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio_np).unsqueeze(0)

        fs = audio_data.sample_rate
        if fs != 16000:
            resampler = T.Resample(orig_freq=fs, new_freq=16000)
            tensor = resampler(tensor)

        return tensor

    def load_profile_tensor(self):
        fs, prof_audio = wav.read(self.profile_wav)
        prof_audio = prof_audio.astype(np.float32) / 32768.0
        tensor = torch.from_numpy(prof_audio).unsqueeze(0)

        if fs != 16000:
            resampler = T.Resample(orig_freq=fs, new_freq=16000)
            tensor = resampler(tensor)

        self.profile_tensor = tensor

    def show_settings(self):
        lines = Text()
        for key in settings.settings:
            if key == "zen_api_key":
                val = settings.settings[key]
                val_txt = ('*' * len(val)) if isinstance(val, str) and val else "(пусто)"
                lines.append(f"  {key}  ", style="bold #89b4fa")
                lines.append(f"{val_txt}\n", style="#cdd6f4")
            else:
                lines.append(f"  {key}  ", style="bold #89b4fa")
                lines.append(f"{settings.settings[key]}\n", style="#cdd6f4")
        prov_label = "OpenCode Zen" if self.provider == "zen" else "Ollama"
        lines.append(f"  provider_active  ", style="bold #89b4fa")
        lines.append(f"{prov_label}\n", style="#cdd6f4")
        if self.provider == "zen":
            lines.append(f"  zen_model_active  ", style="bold #89b4fa")
            lines.append(f"{self.zen_model}\n", style="#cdd6f4")
        self.console.print(Panel(lines, title="⚙ НАСТРОЙКИ", border_style="cyan", box=ROUNDED, padding=(0, 1)))

    def create_second_system_prompt(self):
        self.second_system_prompt = "Вот вывод предыдущих команд и указание пользователя: " + self.second_context + """\nЕсли ты считаешь что ты выполнил указание то ответь просто текстом на поставленный user'ом вопрос.
Если ты не считаешь что ты выполнил указание/недовыполнил указание то закончи его выполнение командой,если произошла ошибка то ответь про ошибку текстом.
1. Если нужно выполнить команду, то ответ должен начинаться с command и быть в формате JSON,ОТВЕТ НЕ ДОЛЖЕН СОДЕРЖАТЬ НИЧЕГО ЛИШНЕГО КРОМЕ СЛОВА COMMAND В НАЧАЛЕ И САМОЙ КОМАНДЫ,к некоторым командам НЕ нужны аргументы(пример):
command {"command": "название_команды", "args": {"аргумент1": "значение1", "аргумент2": "значение2"}}. 
2. Если ты хочешь просто ответить текстом, то ответ должен быть просто текстом(пример): Вместо этого тут должен быть твой ответ на запрос user'а.
Вот список доступных команд и их аргуметов: """ + self.commands_ai_and_args
        return self.second_system_prompt

    def parse_ai_command(self, full_command):
        if full_command.startswith("command "):
            command = full_command[len("command "):]
            try:
                command = json.loads(command)
                if command["command"] in self.commands_ai:
                    self.ai_state = "command"
                    res = self.commands_ai[command["command"]]["func"](*list(command["args"].values()))
                    self.ai_state = "speaking" if self.ai_speak else "idle"
                    self._last_cmd = (command, res)
                    self.second_context += "\nAI executed command:   " + command["command"] + "   With args: " + str(command["args"]) + " and result: " + str(res)
                    self.global_context += "\nAI executed command:   " + command["command"] + "   With args: " + str(command["args"]) + " and result: " + str(res)
                    return 0
            except Exception as e:
                self._last_cmd = (None, f"ОШИБКА: {e}")
                self.second_context += "\nAI: " + full_command + "   BUT THERE WAS AN ERROR IN PARSING OR EXECUTING THE COMMAND: " + str(e)
                self.global_context += "\nAI: " + full_command + "   BUT THERE WAS AN ERROR IN PARSING OR EXECUTING THE COMMAND: " + str(e)
                return 0
        else:
            self.global_context += "\nAI: " + full_command
            return 1

    def _render_ai_response(self, raw, formatted=None):
        if raw.startswith("command "):
            formatted = str(self.format_response(raw))
            res = ""
            has_err = False
            if getattr(self, "_last_cmd", None):
                if self._last_cmd[0] is not None:
                    res = self._last_cmd[1]
                else:
                    res = self._last_cmd[1]
                    has_err = True
                self._last_cmd = None
            body = Text()
            body.append(" " + formatted + "\n", style="bold yellow")
            res_str = "" if res is None else str(res)
            if res_str.strip() and not has_err:
                body.append("\n  ─ Результат: ─\n", style="bold #a6e3a1")
                # подсветка терминал-вывода зелёным, обрезка длинного
                shown = res_str if len(res_str) <= 1500 else res_str[:1500] + "\n…(обрезано)"
                body.append(shown, style="bright_green")
            elif has_err and res_str.strip():
                body.append("\n  ─ Ошибка: ─\n", style="bold red")
                body.append(res_str, style="red")
            else:
                body.append("\n  (вывод пустой — команда могла ничего не вернуть)", style="dim")
            self.console.print(Panel(
                body,
                title=f"🤖 {str(self.trigger_word or 'AI').upper()} · Команда выполнена", title_align="left",
                border_style="yellow", box=ROUNDED, padding=(0, 1),
            ))
        else:
            self._panel(f"🤖 {str(self.trigger_word or 'AI').upper()}", raw, style="ai")

    def clear_console(self):
        subprocess.run("clear", shell=True)
        self._banner()

    def select_micro(self):
        mic_list = sr.Microphone.list_microphone_names()
        lines = Text()
        for index, name in enumerate(mic_list):
            lines.append(f"  [{index}] ", style="bold #89b4fa")
            lines.append(f"{name}\n", style="#cdd6f4")
        self.console.print(Panel(lines, title="⚙ ДОСТУПНЫЕ МИКРОФОНЫ", border_style="cyan", box=ROUNDED, padding=(0, 1)))
        try:
            sel = input(Fore.GREEN + "  Введи номер (индекс) микрофона: " + Style.RESET_ALL).strip()
            if not sel.isdigit():
                print(Fore.YELLOW + "Отменено (нужно ввести число-индекс)" + Style.RESET_ALL)
                return
            self.micro_index = int(sel)
            settings.settings["micro_index"] = self.micro_index
            settings.save_settings()
            print(Fore.GREEN + "MICROPHONE SWITCHED TO   " + str(self.micro_index) + "   SUCCESSFULLY" + Style.RESET_ALL)
            print(Fore.BLUE + "PLEASE RESTART THE PROGRAM TO APPLY THE CHANGES" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + "ERROR CHOOSING THE MICROPHONE:  " + str(e) + Style.RESET_ALL)

    def select_tts_voice(self):
        voices = self.tts.get_available_speakers()
        sel = self._choice_menu("ДОСТУПНЫЕ ГОЛОСА TTS", voices, "Выбери голос (номер): ")
        if sel is None:
            return
        self.tts_voice = sel[0]
        settings.settings["tts_voice"] = self.tts_voice
        settings.save_settings()
        print(Fore.GREEN + "TTS VOICE SWITCHED TO   " + self.tts_voice + "   SUCCESSFULLY" + Style.RESET_ALL)

    def select_whisper_model(self):
        if self.stt_mode != "google":
            self.whisper_models = available_models()
            sel = self._choice_menu("МОДЕЛИ WHISPER", self.whisper_models, "Выбери модель (номер): ")
            if sel is None:
                return
            self.whisper_model = sel[0]
            if self.whisper_model in self.whisper_models:
                self.whisper_load_model = WhisperModel(self.whisper_model, device="cuda", compute_type="float32")
                settings.settings["whispermodel"] = self.whisper_model
                settings.save_settings()
                print(Fore.GREEN + "WHISPER MODEL SWITCHED TO   " + self.whisper_model + "   SUCCESSFULLY" + Style.RESET_ALL)
            else:
                print(Fore.YELLOW + "UNKNOWN MODEL NAME" + Style.RESET_ALL)

    def select_ai_model(self):
        if self.provider == "zen":
            self.select_zen_model()
            return
        self.models_info = ollama.list()
        self.models = [model['name'] for model in self.ollama_data['models']]
        sel = self._choice_menu("МОДЕЛИ OLLAMA", self.models, "Выбери модель (номер): ")
        if sel is None:
            return
        self.model = sel[0]
        settings.settings["model"] = self.model
        settings.settings["provider"] = "ollama"
        self.provider = "ollama"
        settings.save_settings()
        print(Fore.GREEN + "MODEL SWITCHED TO   " + self.model + "   SUCCESSFULLY" + Style.RESET_ALL)
        self.user_prompt = None

    def select_provider(self):
        """Переключает провайдера между ollama и opencode zen."""
        providers = ["ollama  (локальные модели)", "zen  (OpenCode Zen, облачные модели)"]
        sel = self._choice_menu("ПРОЦЕССОР ИИ (провайдер)", providers, "Выбери номер провайдера: ")
        if sel is None:
            return
        choice = sel[0]
        try:
            if choice.startswith("ollama"):
                self.provider = "ollama"
                print(Fore.GREEN + "PROVIDER SWITCHED TO OLLAMA" + Style.RESET_ALL)
                if not self.model:
                    self.select_ai_model()
            elif choice.startswith("zen"):
                self.provider = "zen"
                print(Fore.GREEN + "PROVIDER SWITCHED TO OPENCODE ZEN" + Style.RESET_ALL)
                if not self.zen_api_key:
                    print(Fore.YELLOW + "ZEN API KEY IS EMPTY — задай его командой /zen_api" + Style.RESET_ALL)
                    self.set_zen_api_key()
            else:
                print(Fore.YELLOW + "UNKNOWN INPUT" + Style.RESET_ALL)
                return
        except Exception as e:
            print(Fore.RED + f"ERROR: {e}" + Style.RESET_ALL)
            return
        settings.settings["provider"] = self.provider
        settings.save_settings()
        self.user_prompt = None

    def set_zen_api_key(self):
        print(Fore.CYAN + "INPUT OPENCODE ZEN API KEY: >> " + Style.RESET_ALL, end="")
        key = str(input()).strip()
        if not key:
            print(Fore.YELLOW + "Empty key, cancel" + Style.RESET_ALL)
            return
        self.zen_api_key = key
        self.provider = "zen"
        settings.settings["zen_api_key"] = key
        settings.settings["provider"] = "zen"
        settings.save_settings()
        print(Fore.GREEN + "ZEN API KEY SAVED. Provider switched to zen." + Style.RESET_ALL)

    def select_zen_model(self):
        """Выбор модели из списка моделей OpenCode Zen (через эндпоинт /models)."""
        models = []
        try:
            headers = {}
            if self.zen_api_key:
                headers["Authorization"] = f"Bearer {self.zen_api_key}"
            r = requests.get(self.zen_models_url, headers=headers, timeout=15)
            data = r.json()
            models = [m.get("id", m) for m in data] if isinstance(data, list) else \
                     ([m.get("id") for m in data.get("data", [])] if "data" in data else [])
        except Exception as e:
            print(Fore.YELLOW + f"Не удалось получить список моделей Zen ({e})." + Style.RESET_ALL)
            models = []
        if models:
            sel = self._choice_menu("МОДЕЛИ OPENCODE ZEN", models, "Выбери модель (номер) или впиши имя: ")
            if sel is None:
                # пользователь ввёл не номер — даём возможность вписать имя вручную
                inpraw = input(Fore.CYAN + "  Впиши имя модели (пусто — отмена): " + Style.RESET_ALL).strip()
                if not inpraw:
                    return
                self.zen_model = inpraw
            else:
                self.zen_model = sel[0]
        else:
            name_in = input(Fore.CYAN + "INPUT ZEN MODEL NAME (e.g. gpt-5.4-mini, gpt-4.1-mini): >> " + Style.RESET_ALL).strip()
            if not name_in:
                return
            self.zen_model = name_in
        self.provider = "zen"
        settings.settings["zen_model"] = self.zen_model
        settings.settings["provider"] = "zen"
        settings.save_settings()
        self._panel("☑ МОДЕЛЬ ZEN", f"Установлена модель: [bold]{self.zen_model}[/bold]", style="ok")
        self.user_prompt = None

    def create_prompt(self):
        if self.second_context != "USER:  " + self.user_prompt:
            return self.global_context + "\n\n\n" + self.create_second_system_prompt() + "\nОТВЕЧАЙ НА ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ ИЛИ ДЕЛАЙ ТО ЧТО СКАЗАЛ ПОЛЬЗОВАТЕЛЬ В ТЕКУЩЕМ ЗАПРОСЕ"
        else:
            return self.global_context + "\n\n\n" + "Вот запрос пользователя:  " + self.user_prompt + "\n" + "Вот системное указание для тебя: " + self.system_prompt + "\nОТВЕЧАЙ НА ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ ИЛИ ДЕЛАЙ ТО ЧТО СКАЗАЛ ПОЛЬЗОВАТЕЛЬ В ТЕКУЩЕМ ЗАПРОСЕ"

    def open_menu(self):
        list_keys = list(self.user_commands.keys())
        list_values = list(self.user_commands.values())
        lines = Text("МЕНЮ LUCH\n\n", style="bold cyan")
        for i, key in enumerate(list_keys):
            lines.append(f"  {i + 1}. {key}  ", style="bold #89b4fa")
            lines.append(f"— {list_values[i][1]}\n", style="#6c7086")
        lines.append(f"\n  {len(list_keys) + 1}. Continue to chat", style="bold green")
        self.console.print(Panel(lines, title="⚙️ МЕНЮ", border_style="cyan", box=ROUNDED, padding=(0, 1)))
        provider_label = "OpenCode Zen" if self.provider == "zen" else "Ollama"
        menu_choice = int(input(Fore.GREEN + f"[{provider_label}] INPUT THE NUMBER OF YOUR CHOICE: >> " + Style.RESET_ALL))
        if menu_choice == len(list_keys) + 1:
            print(Fore.GREEN + "CONTINUING TO CHAT WITH THE CURRENT MODEL" + Style.RESET_ALL)
            pass
        else:
            try:
                list_values[menu_choice - 1][0]()
            except Exception as e:
                print(f"Error choosing command: {e}")

    def generate_ai_response(self):
        self.response = ""
        if self.provider == "zen":
            self._generate_zen()
        else:
            self._generate_ollama()

    def _generate_ollama(self):
        # Формируем payload точно так же, как вы делали
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": self.create_prompt()}],
            "stream": True,
            "options": {
                "think": False,
                "num_predict": 512
            }
        }
        
        # Отправляем POST‑запрос на эндпоинт /api/chat
        response_text = ""
        try:
            with requests.post(self.ollama_url + "chat", json=payload, stream=True, timeout=120) as r:
                r.raise_for_status()  # если статус не 200 — выбросит исключение
                for line in r.iter_lines(decode_unicode=True):
                    if line:   # пропускаем пустые строки (kseep-alive)
                        try:
                            chunk = json.loads(line)
                            # извлекаем содержимое из потока
                            if 'message' in chunk and 'content' in chunk['message']:
                                response_text += chunk['message']['content']
                        except json.JSONDecodeError:
                            # если вдруг пришёл невалидный JSON — игнорируем
                            continue
        except Exception as e:
            print(Fore.RED + f"Ollama error: {e}" + Style.RESET_ALL)
            response_text = (f"Не удалось получить ответ от Ollama: {e}. "
                             f"Проверь, что Ollama запущена (localhost:11434) и модель '{self.model}' загружена.")
        self.response = response_text

    def _generate_zen(self):
        """Обращение к OpenCode Zen (OpenAI-совместимый эндпоинт /chat/completions)."""
        if not self.zen_api_key:
            self.response = "Не задан API-ключ OpenCode Zen. Задай его через команду /zen_api или в settings.json."
            print(Fore.RED + "OpenCode Zen: не задан API-ключ" + Style.RESET_ALL)
            return
        payload = {
            "model": self.zen_model,
            "messages": [{"role": "system", "content": self.system_prompt + self.create_second_system_prompt()},
                         {"role": "user", "content": self.create_prompt()}],
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.zen_api_key}",
            "Content-Type": "application/json",
        }
        response_text = ""
        try:
            with requests.post(self.zen_url, json=payload, headers=headers, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        if 'choices' in chunk and chunk['choices']:
                            delta = chunk['choices'][0].get('delta', {})
                            piece = delta.get('content', '')
                            if piece:
                                response_text += piece
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(Fore.RED + f"OpenCode Zen error: {e}" + Style.RESET_ALL)
            response_text = f"Ошибка OpenCode Zen: {e}. Проверь API-ключ и модель '{self.zen_model}'."
        self.response = response_text

    def animation_thinking(self):
        try:
            from rich.live import Live
            from rich.spinner import Spinner
            provider_label = "OpenCode Zen" if self.provider == "zen" else "Ollama"
            with Live(Spinner("dots", text=f" {provider_label} думает..."), refresh_per_second=12, transient=True) as live:
                while self.ai_thread.is_alive():
                    time.sleep(0.05)
        except Exception:
            while self.ai_thread.is_alive():
                for i in range(5):
                    if not self.ai_thread.is_alive():
                        break
                    print(" " * 50, end="\r")
                    print(Fore.MAGENTA + "THINKING" + "." * i + Style.RESET_ALL, end="\r")
                    time.sleep(0.08)
            print(" " * 50, end="\r")

    def play_response(self):
        self.ai_state = "speaking"
        sound = pygame.mixer.Sound(settings.PATHS["response_path"])
        sound_duration = int(sound.get_length() * 1000)
        sound.play()
        pygame.time.wait(sound_duration)
        if self.ai_speak == True:
            self.ai_speak = False
        self.ai_state = "idle"

    def play_timer_tts(self, text, path):
        """Эта функция вызывается из work_fuctions, когда срабатывает таймер"""
        try:
            self.tts.tts(text, path)
            fast_path = "timer_fast.wav"
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "quiet",
                "-i", path, "-filter:a", f"atempo={self.speed_ai_speak}", fast_path
            ])
            os.replace(fast_path, path)
            sound = pygame.mixer.Sound(path)
            sound.play()
        except Exception as e:
            print(f"Timer TTS error: {e}")

    def full_relese_response(self):
        self.second_context = "USER:  " + self.user_prompt
        self.global_context += "\nUSER:  " + self.user_prompt
        if "заблокируй компьютер" in self.user_prompt or "заблокируй пк" in self.user_prompt or "заблокируй комп" in self.user_prompt:
            work_fuctions.lock_pc()
            self.user_prompt = None
            pass
        if len(self.global_context) > 1000:
            us_metka = self.global_context.find("USER:")
            self.global_context = self.global_context[us_metka:]
        self.ai_thread = threading.Thread(target=self.generate_ai_response, daemon=True)
        self.ai_state = "thinking"
        self.ai_thread.start()
        self.animation_thinking()
        if self.ai_thread and self.ai_thread.is_alive():
            self.ai_thread.join()
        i2 = self.parse_ai_command(self.response)
        self._render_ai_response(self.response)
        if i2 == 1:
            self.tts.tts(self.response, settings.PATHS["response_path"])
            subprocess.run([
                "ffmpeg",
                "-y",
                "-loglevel", "quiet",
                "-i", settings.PATHS["response_path"],
                "-filter:a", f"atempo={self.speed_ai_speak}",
                "response_fast.wav"
            ])
            os.replace("response_fast.wav", settings.PATHS["response_path"])
            self.speak_thread = threading.Thread(target=self.play_response, daemon=True)
            self.speak_thread.start()
            self.ai_speak = True
            self.ai_state = "speaking"
        while i2 == 0:
            self.ai_thread = threading.Thread(target=self.generate_ai_response, daemon=True)
            self.ai_state = "thinking"
            self.ai_thread.start()
            self.animation_thinking()
            self.ai_thread.join()
            i2 = self.parse_ai_command(self.response)
            self._render_ai_response(self.response)
            if i2 == 1:
                self.tts.tts(self.response, settings.PATHS["response_path"])
                subprocess.run([
                    "ffmpeg",
                    "-y",
                    "-loglevel", "quiet",
                    "-i", settings.PATHS["response_path"],
                    "-filter:a", f"atempo={self.speed_ai_speak}",
                    "response_fast.wav"
                ])
                os.replace("response_fast.wav", settings.PATHS["response_path"])
                self.speak_thread = threading.Thread(target=self.play_response, daemon=True)
                self.speak_thread.start()
                self.ai_speak = True
        if not self.ai_speak:
            self.ai_state = "idle"
        self.user_prompt = None
        self.response_ready_event.set()
        print("\n" + Fore.WHITE + "USER: >> " + Style.RESET_ALL, end="")

    def listen_user(self, from_file=False):
        recognizer = sr.Recognizer()

        def process_audio(audio):
            self.ai_state = "listening"
            text = ""
            self.is_voice_success = False

            if not from_file:
                with open(settings.PATHS["temp_wav_file"], "wb") as f:
                    f.write(audio.get_wav_data())

            temp_tensor = self.get_audio_tensor(audio)
            score, prediction = self.voice_verifier.verify_batch(self.profile_tensor, temp_tensor)

            if self.stt_mode == "whisper":
                try:
                    segments, info = self.whisper_load_model.transcribe(
                        settings.PATHS["temp_wav_file"],
                        language="ru"
                    )
                    text = " ".join([segment.text for segment in segments]).strip()
                except Exception as e:
                    print(e)
                    text = ""
            elif self.stt_mode == "google":
                try:
                    with sr.AudioFile(settings.PATHS["temp_wav_file"]) as audio_file:
                        audio_data = recognizer.record(audio_file)
                        text = recognizer.recognize_google(audio_data, language="ru-RU")
                except Exception as e:
                    print(e)
                    text = ""

            if prediction.item() is True:
                if not self.ai_speak:
                    if text and self.user_prompt is None:
                        has_trigger = text[0:len(self.trigger_word)].lower() == self.trigger_word.lower()

                        if self.ai_thread.is_alive() == False and has_trigger:
                            self.type_work = "voice"
                            print(Fore.MAGENTA + f"[VOICE MATCHED]: {text}" + Style.RESET_ALL)

                            # Отрезаем триггер-слово из текста перед отправкой в ИИ
                            clean_prompt = text[len(self.trigger_word):].strip(" ,.!?-")
                            self.user_prompt = clean_prompt if clean_prompt else "Привет!"

                            self.full_relese_response()
                            self.type_work = "chat"
                            self.is_voice_success = True
                        elif not has_trigger:
                            print(Fore.YELLOW + f"[TRIGGER MISSING]: Фраза '{text}' проигнорирована (нет триггер-слова)." + Style.RESET_ALL)
                            self.response = f"Сообщение проигнорировано: отсутствует триггер-слово '{self.trigger_word}'."
                            self.ai_state = "idle"
                            self.ignore_response = True   
                else:
                    if text:
                        for frase in self.stop_speak_flags:
                            if frase in text.lower():
                                self.ai_speak = False
                                pygame.mixer.stop()
                                self.stop_audio_triggered = True
                                self.response = ""
                                return
            else:
                print(Fore.RED + f"[ACCESS DENIED] Чужой голос! Score: {score.item():.4f}" + Style.RESET_ALL)
                with open("phrases_not_spoken_in_my_voice.txt", "a", encoding="utf-8") as f:
                    f.write(text + "\n")
                self.response = "Доступ запрещен: ваш голос не совпадает с владельцем."
                self.ai_state = "idle"
                self.ignore_response = True   

        if from_file:
            wav_path = settings.PATHS["temp_wav_file"]
            if not os.path.exists(wav_path):
                self.response = "Файл записи не найден"
                self.response_ready_event.set()
                return
            try:
                with sr.AudioFile(wav_path) as source:
                    audio = recognizer.record(source)
                process_audio(audio)
            except Exception as e:
                print(Fore.RED + f"Ошибка чтения файла: {e}" + Style.RESET_ALL)
                self.response = f"Ошибка обработки: {e}"
            finally:
                self.response_ready_event.set()
        else:
            # Обычное прослушивание микрофона ПК в бесконечном цикле
            recognizer.pause_threshold = 1.5
            with sr.Microphone(device_index=self.micro_index, sample_rate=48000, chunk_size=2048) as source:
                recognizer.adjust_for_ambient_noise(source, duration=2)
                while True:
                    audio = recognizer.listen(source)
                    process_audio(audio)

    def process_command(self, cmd):
        cmd = cmd.strip()
        if cmd.startswith("/") and cmd[1:] in self.user_commands:
            self.user_commands[cmd[1:]][0]()
            return "OK"
        return "UNKNOWN COMMAND"

    def wait_input(self):
        while True:
            if self.user_prompt is None:
                self.user_prompt = input()

    def chat(self):
        if self.whisper_model is None or self.whisper_model == "":
            print("\n" + Fore.YELLOW + "PLEASE SELECT WHISPER MODEL")
            self.select_whisper_model()

        self.whisper_thread = threading.Thread(target=self.listen_user, daemon=True)
        if self.whisper_thread.is_alive() == False:
            self.whisper_thread.start()

        print(Fore.WHITE + "USER: >> ", end="")

        self.input_thread = threading.Thread(target=self.wait_input, daemon=True)
        if self.input_thread.is_alive() == False:
            self.input_thread.start()

        while True:
            time.sleep(0.001)

            # Обработка записи с веб-сервера через listen_user(from_file=True)
            if self.pending_voice:
                self.pending_voice = False
                self.listen_user(from_file=True)

            # Обработка текстовых команд и ввода с клавиатуры
            if self.user_prompt is not None and self.user_prompt != "":
                self.second_system_prompt = ""
                self.second_context = ""
                if self.user_prompt.strip()[0] == "/":
                    if self.user_prompt.strip()[1:] in self.user_commands:
                        self.user_commands[self.user_prompt.strip()[1:]][0]()
                        print(Fore.WHITE + "USER: >> ", end="")
                        self.user_prompt = None
                    else:
                        print(Fore.YELLOW + "UNKNOWN COMMAND" + Style.RESET_ALL)
                        self.user_prompt = None
                        print(Fore.WHITE + "USER: >> ", end="")
                else:
                    need_model = (self.provider != "zen") and self.model == ""
                    if self.provider == "zen" and not self.zen_api_key:
                        print("\n" + Fore.YELLOW + "PLEASE SET ZEN API KEY")
                        self.set_zen_api_key()
                    elif need_model:
                        print("\n" + Fore.YELLOW + "PLEASE SELECT AI MODEL")
                        self.select_ai_model()
                    elif self.ai_thread.is_alive() == False and self.type_work == "chat":
                        self.type_work = "chat"
                        self.full_relese_response()

if __name__ == "__main__":
    AI = AIconsole()
    AI.server_thread = threading.Thread(
        target=web_server.start_server_in_thread, 
        args=(AI,), 
        daemon=True
    )
    AI.server_thread.start()
    AI.chat()
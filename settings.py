from pathlib import Path
import json

PATHS ={
    "settings_path" : "settings.json",
    "voice_profile_path" : "my_voice_profile.wav",
    "memory_path" : "memory.txt",
    "response_path" : "response.wav",
    "temp_wav_file" : "temp.wav"
}

default_settings = {"model": "", 
                    "provider": "ollama",
                    "zen_api_key": "",
                    "zen_model": "gpt-5.4-mini",
                    "whispermodel":"", 
                    "micro_index": 1, 
                    "tts_voice": "xenia", 
                    "trigger_word":"",
                    "speed_ai_speak": 1.0,
                    "stt_mode":"google"
                    }

def get_settings_from_file():
    if Path(PATHS["settings_path"]).is_file():
        try:
            with open(Path(PATHS["settings_path"]), "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as e:
            print(f"Error reading settings file: {e}")
            return {}
    else:
        try:
            with open(Path(PATHS["settings_path"]),"w", encoding="utf-8") as file:
                json.dump(default_settings, file, ensure_ascii=False, indent=4)
            return default_settings
        except Exception as e:
                print(f"Error creating settings file: {e}")
                return default_settings

def save_settings():
    with open(Path(PATHS["settings_path"]),"w",encoding="utf-8") as file:
        json.dump(settings,file,ensure_ascii=False, indent=4)

settings = get_settings_from_file()

stop_speak_flags = [
            "стоп", "стоп мне неприятно", "стоп хватит", "остановись", "остановить", "останови", "останови речь", "останови ответ", "останови озвучку", "останови разговор",
            "замолчи", "замолчи пожалуйста", "замолкни", "молчи", "помолчи", "тихо", "тише", "можно тише", "будь тише", "заткнись",
            "заткнись пожалуйста", "заткнись уже", "закрой рот", "хватит", "хватит говорить", "хватит болтать", "хватит уже", "достаточно", "довольно", "всё хватит",
            "все хватит", "перестань", "перестань говорить", "перестань болтать", "перестань отвечать", "прекрати", "прекрати говорить", "прекрати ответ", "прекрати озвучку", "прекрати болтать",
            "конец", "закончи", "заканчивай", "заверши", "отмена", "отбой", "не надо", "не продолжай", "не отвечай", "не говори",
            "не нужно", "достаточно спасибо", "всё", "все", "стоп ответ", "остановка", "пауза", "сделай паузу", "поставь на паузу", "замри",
            "хорош уже", "хорош", "угомонись", "успокойся", "тихо тихо", "замолчи уже", "хватит уже говорить", "прекрати уже", "всё понятно", "все понятно",
            "я понял", "я понял спасибо", "понятно", "ясно", "ясно спасибо", "спасибо хватит", "спасибо достаточно", "можешь замолчать", "можешь помолчать", "можешь остановиться",
            "можешь прекратить", "можно остановиться", "можно прекратить", "остановись пожалуйста", "прекрати пожалуйста", "замолчи на секунду", "помолчи немного", "помолчи секунду", "тише пожалуйста", "затихни",
            "прервись", "прерви ответ", "прерви озвучку", "выключи голос", "выключи озвучку", "отключи голос", "отключи озвучку","ебало офни"
        ]
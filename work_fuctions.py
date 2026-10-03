import math
import requests as http_requests
import subprocess
import sys
import threading
import re
from datetime import datetime, timedelta
from colorama import Fore, Back, Style
from ddgs import DDGS
from ultralytics import YOLO

# --- Связь с основным процессом и вебом ---
tts_callback = None  # Сюда main.py передаст функцию генерации голоса ИИ
web_alerts = []      # Очередь уведомлений для веб-интерфейса

# --- Модуль геолокации / навигатора ---
# Хранит последние координаты клиента, историю и флаг запроса позиции.
LOCATION_DEFAULT = {"lat": None, "lng": None, "accuracy": None, "timestamp": None, "source": None}
location_data = dict(LOCATION_DEFAULT)   # текущая позиция клиента (обновляется с сайта)
route_data = None                        # точка назначения: {"lat":.., "lng":.., "label":..}
location_history = []                    # история перемещений (список позиций)
location_request_pending = False         # если True — фронт должен прислать свежие координаты

_GEO_UA = "LUCH-AI/1.6 (voice assistant; geolocation tracker)"


def update_location(lat, lng, accuracy=None, source="web"):
    """Сохранить текущую позицию клиента. lat/lng приводятся к float.
    В историю пишется только при сдвиге > 2 м от последней точки (фильтр шума GPS)."""
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return "ERROR: invalid coordinates."
    prev = dict(location_data)   # копия ДО обновления (иначе ссылалась бы на тот же словарь)
    location_data.update({
        "lat": lat,
        "lng": lng,
        "accuracy": float(accuracy) if accuracy is not None else None,
        "timestamp": datetime.now().isoformat(),
        "source": source,
    })
    # Шум: не спамим историю одинаковыми точками
    if prev.get("lat") is not None:
        if haversine(prev["lat"], prev["lng"], lat, lng) > 2.0:
            location_history.append(dict(location_data))
    else:
        location_history.append(dict(location_data))
    # Ограничение истории, чтобы она не росла без предела
    if len(location_history) > 5000:
        del location_history[: len(location_history) - 5000]
    return "LOCATION UPDATED"


def get_location():
    """Вернуть текущую позицию клиента словарём."""
    return {k: location_data[k] for k in location_data}


def reset_location():
    location_data.update(dict(LOCATION_DEFAULT))
    return "LOCATION RESET"


# ---- Геоинструменты для ИИ ----

def haversine(lat1, lng1, lat2, lng2):
    """Расстояние между двумя координатами в метрах (формула гаверсинусов)."""
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def geocode(query):
    """Геокодирование: текстовый адрес/место → координаты (Nominatim/OSM)."""
    try:
        r = http_requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 3, "addressdetails": 0},
            headers={"User-Agent": _GEO_UA}, timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return {"status": "error", "message": f"Ничего не найдено по запросу '{query}'"}
        results = [
            {"name": d.get("display_name"), "lat": float(d["lat"]), "lng": float(d["lon"]),
             "type": d.get("type") or d.get("class")}
            for d in data[:3]
        ]
        return {"status": "ok", "query": query, "results": results}
    except Exception as e:
        return {"status": "error", "message": f"Ошибка геокодирования: {e}"}


def reverse_geocode(lat, lng):
    """Обратное геокодирование: координаты → адрес (Nominatim/OSM)."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Некорректные координаты."}
    try:
        r = http_requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": _GEO_UA}, timeout=15,
        )
        r.raise_for_status()
        d = r.json()
        # Пытаемся собрать максимально точный адрес (дом, улица, город)
        addr = d.get("address") or {}
        parts = []
        for key in ("house_number", "road", "pedestrian", "suburb", "city", "town", "village", "county", "state", "country"):
            if addr.get(key):
                parts.append(addr[key])
        precise = ", ".join(parts) or (d.get("display_name") or "адрес не определён")
        return {"status": "ok", "lat": lat, "lng": lng,
                "address": precise, "house": addr.get("house_number"), "road": addr.get("road")}
    except Exception as e:
        return {"status": "error", "message": f"Ошибка обратного геокодирования: {e}"}


def request_location():
    """Запросить у клиента свежие координаты. Фронт оповестится и пришлёт их."""
    global location_request_pending
    location_request_pending = True
    return {"status": "location_requested",
            "message": "Клиенту отправлен запрос координат. Подожди немного и вызови get_my_location повторно."}


def get_my_location():
    """Текущая позиция клиента (с адресом, если удалось определить)."""
    loc = get_location()
    if loc.get("lat") is None or loc.get("lng") is None:
        return {"status": "error",
                "message": "Текущая позиция не определена. Используй request_location или попроси клиента открыть карту."}
    try:
        rev = reverse_geocode(loc["lat"], loc["lng"])
        address = rev.get("address") if rev.get("status") == "ok" else None
    except Exception:
        address = None
    return {"status": "ok", "lat": loc["lat"], "lng": loc["lng"],
            "accuracy_m": loc.get("accuracy"), "timestamp": loc.get("timestamp"),
            "address": address}


def build_route(destination):
    """Построить маршрут от текущей позиции клиента до цели (OSRM).
    Возвращает расстояние, время, полную геометрию и шаги (маневры)."""
    global route_data
    loc = get_location()
    if loc.get("lat") is None:
        return {"status": "error",
                "message": "Текущая позиция не определена. Используй request_location или попроси клиента открыть карту."}
    g = geocode(destination)
    if g.get("status") != "ok":
        return g
    d = g["results"][0]
    dlat, dlng = d["lat"], d["lng"]
    slat, slng = loc["lat"], loc["lng"]
    route_data = {"lat": dlat, "lng": dlng, "label": destination}
    try:
        r = http_requests.get(
            f"https://router.project-osrm.org/route/v1/driving/{slng},{slat};{dlng},{dlat}",
            params={"overview": "full", "steps": "true", "geometries": "geojson", "alternatives": "false"},
            headers={"User-Agent": _GEO_UA}, timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("routes"):
            return {"status": "error", "message": "OSRM не вернул маршрут."}
        route = data["routes"][0]
        geometry = route.get("geometry", {}).get("coordinates", [])
        # OSRM geometry — [[lng,lat],...], переворачиваем в [lat,lng]
        geometry = [[float(c[1]), float(c[0])] for c in geometry]
        steps = route.get("legs", [{}])[0].get("steps", [])
        return {
            "status": "ok",
            "destination": destination,
            "destination_name": d["name"],
            "destination_coords": {"lat": dlat, "lng": dlng},
            "from": {"lat": slat, "lng": slng},
            "distance_km": round(route.get("distance", 0) / 1000, 2),
            "duration_min": round(route.get("duration", 0) / 60, 1),
            "geometry": geometry,
            "steps": steps,
            "note": "Возможен только автомобильный маршрут.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Ошибка построения маршрута: {e}"}


# ---- Полноценный навигатор с голосовыми подсказками ----
navigation_data = {
    "active": False,
    "destination": None,
    "geometry": [],
    "steps": [],
    "next_maneuver": None,
    "last_announced": -1,
    "early_announced": set(),
    "started_at": None,
}
_nav_stop_evt = threading.Event()


def _maneuver_text(step):
    """Человекопонятная инструкция из шага маршрута OSRM."""
    m = step.get("maneuver", {})
    typ = m.get("type")
    mod = m.get("modifier")
    name = step.get("name") or ""
    actions = {
        "departure": "начали движение",
        "arrival": "вы прибыли в пункт назначения",
        "turn": "поверните",
        "continue": "продолжайте движение",
        "merge": "вливайтесь в поток",
        "fork": "держитесь",
        "end of road": "в конце дороги поверните",
        "roundabout": "двигайтесь по кругу",
        "roundabout turn": "по кругу поверните",
        "new name": "продолжайте движение",
        "on ramp": "выезжайте на съезд",
        "off ramp": "сверните на съезд",
        "use lane": "держите свою полосу",
        "restricted": "двигайтесь по разрешённому маршруту",
        "uturn": "развернитесь",
    }
    dirs = {
        "left": "налево", "right": "направо",
        "sharp left": "резко налево", "sharp right": "резко направо",
        "slight left": "плавно налево", "slight right": "плавно направо",
        "straight": "прямо", "uturn": "развернитесь",
    }
    if typ == "arrival":
        return actions["arrival"]
    act = actions.get(typ, "продолжайте движение")
    direction = dirs.get(mod, "")
    text = f"{act} {direction}".strip()
    if name and typ not in ("departure",):
        text += f" на {name}"
    return text


def _find_next_maneuver(loc_lat, loc_lng):
    """Какой шаг маршрута сейчас актуален и сколько м до его маневра."""
    steps = navigation_data.get("steps") or []
    for i in range(navigation_data["last_announced"] + 1, len(steps)):
        step = steps[i]
        m = step.get("maneuver", {})
        if m.get("type") in ("departure",):
            continue
        lat = m.get("location", [None, None])
        if not lat or lat[0] is None:
            continue
        mlat, mlng = float(lat[1]), float(lat[0])
        dist = haversine(loc_lat, loc_lng, mlat, mlng)
        return i, step, dist
    return None, None, None


def _nav_loop():
    """Фоновый цикл навигатора: следит за позицией и озвучивает манёвры."""
    global navigation_data
    while not _nav_stop_evt.wait(3):
        loc = get_location()
        if loc.get("lat") is None:
            continue
        steps = navigation_data.get("steps") or []
        if not steps:
            continue
        i, step, dist = _find_next_maneuver(loc["lat"], loc["lng"])
        if step is None:
            continue
        m = step.get("maneuver", {})
        typ = m.get("type", "")

        # Конец маршрута: пункт назначения рядом
        if typ == "arrival" and dist < 80:
            if navigation_data["last_announced"] < i:
                navigation_data["last_announced"] = i
                text = _maneuver_text(step)
                if tts_callback:
                    tts_callback(text, "/tmp/nav_arrival.wav")
                navigation_data["next_maneuver"] = None
            continue

        # Раннее предупреждение за ~300 м (один раз)
        if 90 <= dist <= 300 and i not in navigation_data["early_announced"]:
            navigation_data["early_announced"].add(i)
            text = f"Через {int(round(dist / 10) * 10)} метров {_maneuver_text(step)}"
            navigation_data["next_maneuver"] = {"text": text, "distance_m": int(dist), "index": i}
            if tts_callback and typ not in ("arrival",):
                tts_callback(text, "/tmp/nav_early.wav")

        # Непосредственно манёвр: подходим ближе 70 м
        if dist < 70 and navigation_data["last_announced"] < i:
            navigation_data["last_announced"] = i
            text = _maneuver_text(step)
            navigation_data["next_maneuver"] = {"text": text, "distance_m": int(dist), "index": i}
            if tts_callback and typ not in ("arrival",):
                tts_callback(text, "/tmp/nav_turn.wav")


def start_navigation(destination):
    """Полноценный навигатор: строит маршрут и голосом ведёт по нему."""
    global navigation_data
    route = build_route(destination)
    if route.get("status") != "ok":
        return route
    # останавливаем предыдущую навигацию, если была
    _nav_stop_evt.set()
    _nav_stop_evt.clear()
    navigation_data.update({
        "active": True,
        "destination": destination,
        "destination_coords": route["destination_coords"],
        "geometry": route["geometry"],
        "steps": route["steps"],
        "next_maneuver": None,
        "last_announced": -1,
        "early_announced": set(),
        "started_at": datetime.now().isoformat(),
    })
    t = threading.Thread(target=_nav_loop, daemon=True)
    t.start()
    first = _next_maneuver_summary()
    return {
        "status": "navigation_started",
        "destination": destination,
        "destination_coords": route["destination_coords"],
        "distance_km": route["distance_km"],
        "duration_min": route["duration_min"],
        "geometry": route["geometry"],
        "next_maneuver": first,
        "note": "Навигация активна: ЛУЧ будет голосом подсказывать повороты.",
    }


def _next_maneuver_summary():
    """Текущая информация о следующем маневре для статуса/карты."""
    if not navigation_data.get("geometry"):
        return None
    m = navigation_data.get("next_maneuver")
    if m:
        return m
    if navigation_data.get("steps"):
        # первый значимый манёвр маршрута
        for s in navigation_data["steps"]:
            mm = s.get("maneuver", {})
            if mm.get("type") not in ("departure",):
                loc = mm.get("location", [None, None])
                if loc[0] is not None:
                    return {"text": _maneuver_text(s), "distance_m": None, "index": 0}
    return None


def stop_navigation():
    """Остановить голосовую навигацию."""
    _nav_stop_evt.set()
    navigation_data.update({"active": False, "next_maneuver": None})
    return {"status": "navigation_stopped"}


def navigation_status():
    """Текущее состояние навигатора (для веб-карты и ИИ)."""
    loc = get_location()
    current = None
    remaining_m = None
    if navigation_data.get("active") and loc.get("lat") is not None:
        steps = navigation_data.get("steps") or []
        for i in range(navigation_data["last_announced"] + 1, len(steps)):
            m = steps[i].get("maneuver", {})
            lat = m.get("location", [None, None])
            if lat[0] is None:
                continue
            mlat, mlng = float(lat[1]), float(lat[0])
            dist = haversine(loc["lat"], loc["lng"], mlat, mlng)
            remaining = m.get("duration", 0) + steps[i].get("duration", 0)
            remaining_m = int(dist)
            current = {"text": _maneuver_text(steps[i]), "distance_m": int(dist)}
            break
    return {
        "active": navigation_data.get("active", False),
        "destination": navigation_data.get("destination"),
        "destination_coords": navigation_data.get("destination_coords"),
        "geometry": navigation_data.get("geometry", []),
        "next_maneuver": navigation_data.get("next_maneuver") or current,
        "remaining_distance_m": remaining_m,
        "current_location": {"lat": loc.get("lat"), "lng": loc.get("lng")} if loc.get("lat") is not None else None,
    }


def distance_to(lat, lng):
    """Расстояние от текущей позиции клиента до указанной точки (по прямой)."""
    loc = get_location()
    if loc.get("lat") is None:
        return {"status": "error", "message": "Текущая позиция не определена."}
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Некорректные координаты."}
    meters = haversine(loc["lat"], loc["lng"], lat, lng)
    return {"status": "ok",
            "from": {"lat": loc["lat"], "lng": loc["lng"]},
            "to": {"lat": lat, "lng": lng},
            "distance_m": round(meters),
            "distance_km": round(meters / 1000, 2)}


def _overpass_query(query_body, timeout=25):
    """Выполнить запрос к Overpass API, перебирая несколько зеркал."""
    mirrors = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]
    last_err = None
    for mirror in mirrors:
        try:
            r = http_requests.post(mirror, data={"data": query_body},
                                   headers={"User-Agent": _GEO_UA}, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            continue
    raise last_err


def nearby(what, radius=2000):
    """Найти места рядом с клиентом по названию (Overpass API/OSM)."""
    loc = get_location()
    if loc.get("lat") is None:
        return {"status": "error", "message": "Текущая позиция не определена."}
    try:
        radius = max(100, min(int(radius), 20000))
    except (TypeError, ValueError):
        radius = 2000
    escaped = str(what).replace("\\", "\\\\").replace('"', '\\"')
    q = (
        f'[out:json][timeout:20];'
        f'(node["name"~"{escaped}",i](around:{radius},{loc["lat"]},{loc["lng"]});'
        f'way["name"~"{escaped}",i](around:{radius},{loc["lat"]},{loc["lng"]});'
        f'rel["name"~"{escaped}",i](around:{radius},{loc["lat"]},{loc["lng"]}););'
        f'out center 12;'
    )
    try:
        data = _overpass_query(q)
        elems = data.get("elements", [])
    except Exception:
        # Фолбэк: ищем через Nominatim в квадрате вокруг точки
        try:
            dlat = radius / 111000.0
            dlng = radius / (111000.0 * math.cos(math.radians(loc["lat"])))
            r = http_requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": what, "format": "json", "limit": 8, "bounded": 1,
                        "viewbox": f"{loc['lng']-dlng},{loc['lat']-dlat},{loc['lng']+dlng},{loc['lat']+dlat}"},
                headers={"User-Agent": _GEO_UA}, timeout=20,
            )
            r.raise_for_status()
            elems = []
            for item in r.json():
                elems.append({
                    "lat": float(item["lat"]), "lon": float(item["lon"]),
                    "tags": {"name": item.get("display_name", what).split(",")[0],
                             "amenity": item.get("type") or "place"},
                    "dist_m": haversine(loc["lat"], loc["lng"], float(item["lat"]), float(item["lon"])),
                })
        except Exception as e:
            return {"status": "error", "message": f"Ошибка поиска рядом: {e}"}

    if not elems:
        return {"status": "error",
                "message": f"Не найдено мест по запросу '{what}' в радиусе {radius} м."}
    spots = []
    for el in elems:
        lat = el.get("lat")
        lng = el.get("lon")
        if lat is None and "center" in el:
            lat = el["center"].get("lat"); lng = el["center"].get("lon")
        if lat is None or lng is None:
            continue
        t = el.get("tags", {})
        metric = el.get("dist_m")
        if metric is None:
            metric = haversine(loc["lat"], loc["lng"], lat, lng)
        spots.append({
            "name": t.get("name") or what,
            "category": t.get("amenity") or t.get("shop") or t.get("tourism") or t.get("leisure") or "place",
            "distance_m": round(metric),
            "lat": lat, "lng": lng,
        })
    spots = [s for s in spots if s["name"].lower() != what.lower().strip()]
    spots = sorted(spots, key=lambda s: s["distance_m"])[:8]
    if not spots:
        return {"status": "error", "message": f"Рядом с тобой нет мест с именем '{what}'."}
    return {"status": "ok", "query": what, "radius_m": radius,
            "center": {"lat": loc["lat"], "lng": loc["lng"]}, "spots": spots}


def analyze_movement():
    """Анализ истории перемещений: трек, длина пути, диапазон времени, текущая точка."""
    if not location_history or location_history[-1].get("lat") is None:
        return {"status": "error",
                "message": "История перемещений пуста. Клиент ещё ни разу не присылал координаты (нужна открытая карта)."}
    total = 0.0
    prev = None
    unique_pts = 0
    prev_bucket = None
    for p in location_history:
        if p.get("lat") is None:
            prev = None; prev_bucket = None; continue
        cur_bucket = (round(p["lat"], 4), round(p["lng"], 4))
        if cur_bucket != prev_bucket:
            unique_pts += 1
            prev_bucket = cur_bucket
        if prev is not None:
            total += haversine(prev["lat"], prev["lng"], p["lat"], p["lng"])
        prev = p
    fixes = location_history
    return {
        "status": "ok",
        "points_count": len([p for p in fixes if p.get("lat") is not None]),
        "unique_spots": unique_pts,
        "track_length_km": round(total / 1000, 2),
        "first_fix": fixes[0].get("timestamp"),
        "last_fix": fixes[-1].get("timestamp"),
        "current": {"lat": location_data["lat"], "lng": location_data["lng"],
                    "accuracy_m": location_data.get("accuracy")},
    }


def navigator(destination):
    """Полноценный навигатор: маршрут + голосовые подсказки поворотов."""
    return start_navigation(destination)


def stop_navigator():
    """Остановить активную голосовую навигацию."""
    return stop_navigation()


def navigator_status():
    """Текущее состояние навигатора (для голосового запроса)."""
    return navigation_status()


def web_search(request):
    with DDGS() as ddgs:
        return list(ddgs.text(request, max_results=10))

def terminal(command):
    if not command or not command.strip():
        return ""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "ОШИБКА: команда превысила лимит времени 60 секунд."
    except Exception as e:
        return f"ОШИБКА: {e}"
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        combined = (out + "\n" + err).strip()
        return combined or f"ОШИБКА: команда завершилась с кодом {result.returncode}"
    return out or ""

def exit():
    print(Fore.GREEN + "EXIT" + Style.RESET_ALL)
    sys.exit(0)

def lock_pc():
    subprocess.run(["hyprlock"])
    return "BLOCK PC SUCCESSFULLY"

def print_text(text):
    subprocess.run(['wtype', text])
    return "TEXT PRINTED SUCCESSFULLY"

# ---- ТАЙМЕР ----
def timer_alert(description):
    print(Fore.RED + f"\n[АЛАРМ!] Сработал таймер: {description}" + Style.RESET_ALL)

    try:
        subprocess.run(["notify-send", "-u", "critical", "-t", "10000", "LUCH AI ⏰", description])
    except Exception:
        pass
    
    # 2. Генерируем голос ИИ и воспроизводим на ПК локально
    audio_path = "/tmp/timer_alert.wav"
    if tts_callback:
        tts_callback(description, audio_path)
        
    # 3. Передаем сигнал для веб-интерфейса
    web_alerts.append({"description": description})

def set_timer(timer_type, time_val, description):
    now = datetime.now()
    delay_seconds = 0
    
    if timer_type == "absolute":
        try:
            target_time = datetime.strptime(time_val, "%H:%M").time()
            target_dt = datetime.combine(now.date(), target_time)
            if target_dt < now:
                target_dt += timedelta(days=1)
            delay_seconds = (target_dt - now).total_seconds()
        except ValueError:
            return "ERROR: invalid absolute time format."
    elif timer_type == "relative":
        match = re.match(r'^\+?(\d+)([smh])$', time_val.strip().lower())
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if unit == 's': delay_seconds = val
            elif unit == 'm': delay_seconds = val * 60
            elif unit == 'h': delay_seconds = val * 3600
        else:
            return "ERROR: invalid relative time format."
    else:
        return "ERROR: invalid timer_type."

    t = threading.Timer(delay_seconds, timer_alert, args=[description])
    t.start()
    
    return f"TIMER SET SUCCESSFULLY FOR {time_val}"

commands_ai = {
    "terminal": {"func": terminal, "icon": "🖥️"},
    "web_search": {"func": web_search, "icon": "🌐"},
    "lock_pc": {"func": lock_pc, "icon": "🔒"},
    "print_text": {"func": print_text, "icon": "✍️"},
    "set_timer": {"func": set_timer, "icon": "⏰"},
    "navigator": {"func": navigator, "icon": "🗺️"},
    "stop_navigator": {"func": stop_navigator, "icon": "⏹️"},
    "navigator_status": {"func": navigator_status, "icon": "🧭"},
    "get_my_location": {"func": get_my_location, "icon": "📍"},
    "request_location": {"func": request_location, "icon": "📡"},
    "geocode": {"func": geocode, "icon": "🔎"},
    "reverse_geocode": {"func": reverse_geocode, "icon": "🧭"},
    "build_route": {"func": build_route, "icon": "🛣️"},
    "distance_to": {"func": distance_to, "icon": "📏"},
    "nearby": {"func": nearby, "icon": "📌"},
    "analyze_movement": {"func": analyze_movement, "icon": "📊"},
}

commands_ai_and_args = """
    1. terminal - выполнить команду в терминале.
    Пример: {"command": "terminal", "args": {"command": "ls"}}. 
    
    2. web_search - использовать веб поиск по запросу.
    Пример: {"command": "web_search", "args": {"request": "что такое ии"}}. 
    
    3. lock_pc - заблокировать пк.
    Пример: {"command": "lock_pc", "args": {}}. 
    
    4. print_text - сэмитировать печать текста с клавиатуры.
    Пример: {"command": "print_text", "args": {"text":"тут текст"}}. 
    
    5. set_timer - установить таймер. Обязательно укажи описание!
    Пример 1: {"command": "set_timer", "args": {"timer_type": "relative", "time_val": "10m", "description": "Пора выключать плиту"}}. Доступны 's', 'm', 'h'.
    Пример 2: {"command": "set_timer", "args": {"timer_type": "absolute", "time_val": "18:30", "description": "Начинается важный созвон"}}. Указывается в формате HH:MM.

    ГЕОЛОКАЦИЯ И НАВИГАЦИЯ (клиент может присылать свои координаты с телефона/браузера):
    «текущая позиция» — это последние координаты, которые прислал клиент. Если они не определены, сначала вызови request_location.

    6. request_location - запросить у клиента свежие координаты (нужно, если текущая позиция пуста). Затем подожди и повтори get_my_location.
    Пример: {"command": "request_location", "args": {}}.

    7. get_my_location - узнать текущую позицию клиента (координаты, адрес, точность).
    Пример: {"command": "get_my_location", "args": {}}.

    8. geocode - преобразовать текстовый адрес или название места в координаты.
    Пример: {"command": "geocode", "args": {"query": "Москва, Красная площадь"}}.

    9. reverse_geocode - узнать адрес по координатам.
    Пример: {"command": "reverse_geocode", "args": {"lat": 55.7558, "lng": 37.6173}}.

    10. build_route - построить маршрут от текущей позиции клиента до цели (автомобильный, через OSRM). Вернёт расстояние, время, геометрию и список маневров.
    Пример: {"command": "build_route", "args": {"destination": "Казань, Кремль"}}.

    11. navigator - включить полноценный навигатор до цели: ЛУЧ голосом подсказывает повороты по мере движения (дистанции, маневры).
    Пример: {"command": "navigator", "args": {"destination": "Казань, Кремль"}}.
    Вернёт: расстояние, время и первый маневр; дальше ведёт голосом в фоне.

    12. stop_navigator - остановить активную голосовую навигацию. Аргументы не нужны.
    Пример: {"command": "stop_navigator", "args": {}}.

    13. navigator_status - узнать текущее состояние навигатора (активен ли, следующий маневр, остаток пути).
    Пример: {"command": "navigator_status", "args": {}}.

    14. distance_to - расстояние по прямой от текущей позиции клиента до точки.
    Пример: {"command": "distance_to", "args": {"lat": 55.7558, "lng": 37.6173}}.

    15. nearby - найти места (заведения, магазины и т.п.) рядом с клиентом по названию. Аргумент "radius" — радиус в метрах (по умолчанию 2000).
    Пример: {"command": "nearby", "args": {"what": "кофейня", "radius": 3000}}.

    13. analyze_movement - проанализировать историю перемещений клиента: сколько точек и уникальных мест, длина трека, временной диапазон.
    Пример: {"command": "analyze_movement", "args": {}}.
"""
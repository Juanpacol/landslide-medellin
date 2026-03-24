"""Restaura todas las comunas, eventos y alertas en Supabase."""
import os, json, random, math
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

COMUNAS = [
    {"commune_id": "1",  "nombre_comuna": "Popular",             "pendiente_promedio": 28.0, "is_zona_ladera": True,  "coords": [[-75.553,6.298],[-75.535,6.298],[-75.535,6.318],[-75.553,6.318],[-75.553,6.298]]},
    {"commune_id": "2",  "nombre_comuna": "Santa Cruz",          "pendiente_promedio": 22.0, "is_zona_ladera": True,  "coords": [[-75.553,6.278],[-75.535,6.278],[-75.535,6.298],[-75.553,6.298],[-75.553,6.278]]},
    {"commune_id": "3",  "nombre_comuna": "Manrique",            "pendiente_promedio": 24.0, "is_zona_ladera": True,  "coords": [[-75.535,6.278],[-75.515,6.278],[-75.515,6.298],[-75.535,6.298],[-75.535,6.278]]},
    {"commune_id": "4",  "nombre_comuna": "Aranjuez",            "pendiente_promedio": 14.0, "is_zona_ladera": False, "coords": [[-75.565,6.278],[-75.553,6.278],[-75.553,6.298],[-75.565,6.298],[-75.565,6.278]]},
    {"commune_id": "5",  "nombre_comuna": "Castilla",            "pendiente_promedio": 8.0,  "is_zona_ladera": False, "coords": [[-75.585,6.278],[-75.565,6.278],[-75.565,6.298],[-75.585,6.298],[-75.585,6.278]]},
    {"commune_id": "6",  "nombre_comuna": "Doce de Octubre",     "pendiente_promedio": 20.0, "is_zona_ladera": True,  "coords": [[-75.595,6.278],[-75.575,6.278],[-75.575,6.298],[-75.595,6.298],[-75.595,6.278]]},
    {"commune_id": "7",  "nombre_comuna": "Robledo",             "pendiente_promedio": 18.0, "is_zona_ladera": True,  "coords": [[-75.615,6.258],[-75.585,6.258],[-75.585,6.278],[-75.615,6.278],[-75.615,6.258]]},
    {"commune_id": "8",  "nombre_comuna": "Villa Hermosa",       "pendiente_promedio": 21.0, "is_zona_ladera": True,  "coords": [[-75.535,6.238],[-75.515,6.238],[-75.515,6.258],[-75.535,6.258],[-75.535,6.238]]},
    {"commune_id": "9",  "nombre_comuna": "Buenos Aires",        "pendiente_promedio": 19.0, "is_zona_ladera": True,  "coords": [[-75.555,6.228],[-75.535,6.228],[-75.535,6.248],[-75.555,6.248],[-75.555,6.228]]},
    {"commune_id": "10", "nombre_comuna": "La Candelaria",       "pendiente_promedio": 5.0,  "is_zona_ladera": False, "coords": [[-75.575,6.238],[-75.555,6.238],[-75.555,6.258],[-75.575,6.258],[-75.575,6.238]]},
    {"commune_id": "11", "nombre_comuna": "Laureles-Estadio",    "pendiente_promedio": 4.0,  "is_zona_ladera": False, "coords": [[-75.595,6.238],[-75.575,6.238],[-75.575,6.258],[-75.595,6.258],[-75.595,6.238]]},
    {"commune_id": "12", "nombre_comuna": "La América",          "pendiente_promedio": 6.0,  "is_zona_ladera": False, "coords": [[-75.615,6.238],[-75.595,6.238],[-75.595,6.258],[-75.615,6.258],[-75.615,6.238]]},
    {"commune_id": "13", "nombre_comuna": "San Javier",          "pendiente_promedio": 26.0, "is_zona_ladera": True,  "coords": [[-75.635,6.238],[-75.615,6.238],[-75.615,6.258],[-75.635,6.258],[-75.635,6.238]]},
    {"commune_id": "14", "nombre_comuna": "El Poblado",          "pendiente_promedio": 12.0, "is_zona_ladera": False, "coords": [[-75.565,6.188],[-75.535,6.188],[-75.535,6.228],[-75.565,6.228],[-75.565,6.188]]},
    {"commune_id": "15", "nombre_comuna": "Guayabal",            "pendiente_promedio": 7.0,  "is_zona_ladera": False, "coords": [[-75.595,6.188],[-75.565,6.188],[-75.565,6.218],[-75.595,6.218],[-75.595,6.188]]},
    {"commune_id": "16", "nombre_comuna": "Belén",               "pendiente_promedio": 16.0, "is_zona_ladera": True,  "coords": [[-75.625,6.198],[-75.595,6.198],[-75.595,6.228],[-75.625,6.228],[-75.625,6.198]]},
    {"commune_id": "50", "nombre_comuna": "Palmitas",            "pendiente_promedio": 30.0, "is_zona_ladera": True,  "coords": [[-75.678,6.298],[-75.648,6.298],[-75.648,6.338],[-75.678,6.338],[-75.678,6.298]]},
    {"commune_id": "60", "nombre_comuna": "San Cristóbal",       "pendiente_promedio": 26.0, "is_zona_ladera": True,  "coords": [[-75.648,6.258],[-75.618,6.258],[-75.618,6.298],[-75.648,6.298],[-75.648,6.258]]},
    {"commune_id": "70", "nombre_comuna": "Altavista",           "pendiente_promedio": 28.0, "is_zona_ladera": True,  "coords": [[-75.648,6.198],[-75.618,6.198],[-75.618,6.238],[-75.648,6.238],[-75.648,6.198]]},
    {"commune_id": "80", "nombre_comuna": "San Antonio de Prado","pendiente_promedio": 18.0, "is_zona_ladera": True,  "coords": [[-75.648,6.138],[-75.608,6.138],[-75.608,6.178],[-75.648,6.178],[-75.648,6.138]]},
    {"commune_id": "90", "nombre_comuna": "Santa Elena",         "pendiente_promedio": 22.0, "is_zona_ladera": True,  "coords": [[-75.508,6.198],[-75.478,6.198],[-75.478,6.238],[-75.508,6.238],[-75.508,6.198]]},
]

# ── Regenerar eventos ──────────────────────────────────────────
random.seed(42)
tipos = ["Deslizamiento de tierra", "Movimiento en masa", "Deslizamiento", "Movimiento de tierra"]
barrios = ["La Cruz", "El Pinal", "Versalles", "La Honda", "Bello Oriente", "La Sierra",
           "El Faro", "Carpinelo", "La Avanzada", "Granizal"]
comunas_con_eventos = [
    ("1",55),("2",55),("3",61),("4",50),("5",55),("6",50),
    ("7",50),("8",60),("9",56),("13",48),
    ("50",10),("60",15),("70",64),("80",12),("90",8),
]
base_date = datetime(2018, 1, 1)
events = []
idx = 0
for cid, n in comunas_con_eventos:
    for _ in range(n):
        days = random.randint(0, 365*6)
        fecha = (base_date + timedelta(days=days)).strftime("%Y-%m-%d")
        events.append({
            "source_row_id": str(idx),
            "fecha": fecha,
            "tipo_emergencia": random.choice(tipos),
            "commune_id": cid,
            "barrio": random.choice(barrios),
            "latitud": 6.2 + random.uniform(-0.15, 0.15),
            "longitud": -75.57 + random.uniform(-0.1, 0.1),
            "has_coords": True,
        })
        idx += 1

# ── Calcular n_eventos por commune ────────────────────────────
n_map = {}
for e in events:
    cid = e["commune_id"]
    n_map[cid] = n_map.get(cid, 0) + 1

max_n = max(n_map.values()) if n_map else 1

def categoria(n, pend):
    score = (n / max_n) * 0.6 + (min(pend, 30) / 30) * 0.4
    if score < 0.25: return "Bajo"
    if score < 0.50: return "Medio"
    if score < 0.75: return "Alto"
    return "Crítico"

# ── Limpiar y reinsertar communes ─────────────────────────────
print("Limpiando communes...")
sb.table("communes").delete().neq("commune_id", "___").execute()

records = []
for c in COMUNAS:
    n = n_map.get(c["commune_id"], 0)
    pend = c["pendiente_promedio"]
    indice = round((n/max_n)*0.6 + (min(pend,30)/30)*0.4, 4)
    records.append({
        "commune_id": c["commune_id"],
        "nombre_comuna": c["nombre_comuna"],
        "pendiente_promedio": pend,
        "is_zona_ladera": c["is_zona_ladera"],
        "n_eventos": n,
        "indice_riesgo": indice,
        "categoria_riesgo": categoria(n, pend),
        "indice_parcial": False,
        "geometry": json.dumps({"type": "Polygon", "coordinates": [c["coords"]]}),
    })

sb.table("communes").insert(records).execute()
print(f"  {len(records)} comunas insertadas")

# ── Limpiar y reinsertar events ───────────────────────────────
print("Limpiando events...")
sb.table("events").delete().neq("id", 0).execute()
for i in range(0, len(events), 500):
    sb.table("events").insert(events[i:i+500]).execute()
print(f"  {len(events)} eventos insertados")

# ── Regenerar alertas ─────────────────────────────────────────
print("Regenerando alertas...")
sb.table("alerts").delete().neq("id", 0).execute()
now = datetime.now().isoformat()
alerts = []
for r in records:
    if r["is_zona_ladera"] and r["n_eventos"] >= 5:
        nivel = "Rojo" if r["n_eventos"] >= 15 else "Naranja"
        alerts.append({
            "commune_id": r["commune_id"],
            "nivel": nivel,
            "precipitacion_valor": round(17.3 + r["n_eventos"] / 10, 1),
            "tipo_umbral": "acum_7d",
            "timestamp": now,
        })
alerts.sort(key=lambda a: 0 if a["nivel"] == "Rojo" else 1)
sb.table("alerts").insert(alerts).execute()
print(f"  {len(alerts)} alertas insertadas")

# ── Verificación ──────────────────────────────────────────────
c = sb.table("communes").select("commune_id", count="exact").execute()
e = sb.table("events").select("id", count="exact").execute()
a = sb.table("alerts").select("id", count="exact").execute()
print(f"\nResumen: communes={c.count} | events={e.count} | alerts={a.count}")
print("Restauración completa.")

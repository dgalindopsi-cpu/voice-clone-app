"""
App de clonación de voz local.
- Frontend simple servido en /
- /api/tonos          -> lista los tonos disponibles (desde tonos.json)
- /api/generar-texto  -> manda texto + tono a Gemini y devuelve el texto reescrito
- /api/sintetizar     -> toma texto + referencias de voz y genera audio con XTTS v2
- /api/voces          -> lista los clips de referencia disponibles en reference_voices/
- /api/subir-voz      -> sube un nuevo clip de referencia (.wav)

Requiere: GEMINI_API_KEY como variable de entorno.
"""

import json
import os
import uuid
import wave
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# XTTS v2 pide aceptar la licencia CPML (uso no comercial) la primera vez que
# se carga, con un prompt interactivo "y/n" por consola. En un servidor web
# no hay consola esperando input, así que sin esto el proceso se queda
# colgado para siempre en la primera síntesis. Al fijar esta variable acordás
# los términos de la licencia de forma no interactiva: https://coqui.ai/cpml
os.environ.setdefault("COQUI_TOS_AGREED", "1")

BASE_DIR = Path(__file__).parent
REF_VOICES_DIR = BASE_DIR / "reference_voices"
OUTPUT_DIR = BASE_DIR / "output"
TONOS_PATH = BASE_DIR / "tonos.json"

REF_VOICES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Clonador de voz local")


def nombre_seguro(nombre: str) -> str:
    """Reduce un nombre de archivo recibido del cliente a un nombre plano y
    seguro, sin componentes de carpeta, para evitar path traversal
    (ej. '../../otra_carpeta/archivo.wav') al construir rutas en disco."""
    nombre = os.path.basename((nombre or "").replace("\\", "/"))
    if not nombre or nombre in (".", "..") or "/" in nombre or "\\" in nombre:
        raise HTTPException(400, "Nombre de archivo inválido")
    return nombre

# ---------------------------------------------------------------------------
# XTTS v2 — se carga una sola vez al iniciar el servidor
# ---------------------------------------------------------------------------
tts_model = None


def cargar_modelo_tts():
    global tts_model
    if tts_model is None:
        print("Cargando XTTS v2... (puede tardar un poco la primera vez)")
        from TTS.api import TTS
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        print(f"XTTS v2 cargado en: {device}")
    return tts_model


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
def generar_con_gemini(texto: str, instruccion_tono: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "Falta la variable de entorno GEMINI_API_KEY")

    from google import genai
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=api_key)
    prompt = (
        f"{instruccion_tono}\n\n"
        f"Texto original:\n\"{texto}\"\n\n"
        "Devuelve SOLO el texto reescrito, sin comillas, sin explicaciones adicionales."
    )
    try:
        response = client.models.generate_content(
            model="gemini-3.7-flash",
            contents=prompt,
        )
    except genai_errors.APIError as e:
        raise HTTPException(502, f"Error al llamar a Gemini: {e}")

    texto_generado = getattr(response, "text", None)
    if not texto_generado:
        # puede pasar si Gemini bloqueó la respuesta por sus filtros de seguridad
        raise HTTPException(
            502,
            "Gemini no devolvió texto (es posible que haya bloqueado el "
            "contenido por sus filtros de seguridad). Prueba reformular el texto.",
        )
    return texto_generado.strip()


# ---------------------------------------------------------------------------
# Modelos de request
# ---------------------------------------------------------------------------
class GenerarTextoRequest(BaseModel):
    texto: str
    tono: str


class SintetizarRequest(BaseModel):
    texto: str
    voces_referencia: list[str]
    idioma: str = "es"


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/api/tonos")
def listar_tonos():
    with open(TONOS_PATH, encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/generar-texto")
def generar_texto(req: GenerarTextoRequest):
    tonos = json.loads(TONOS_PATH.read_text(encoding="utf-8"))
    instruccion = tonos.get(req.tono)
    if not instruccion:
        raise HTTPException(400, f"Tono '{req.tono}' no existe")
    texto_generado = generar_con_gemini(req.texto, instruccion)
    return {"texto": texto_generado}


@app.get("/api/voces")
def listar_voces():
    archivos = sorted(p.name for p in REF_VOICES_DIR.glob("*.wav"))
    return {"voces": archivos}


@app.post("/api/subir-voz")
async def subir_voz(file: UploadFile = File(...)):
    nombre = nombre_seguro(file.filename)
    if not nombre.lower().endswith(".wav"):
        raise HTTPException(400, "Solo se aceptan archivos .wav")

    destino = REF_VOICES_DIR / nombre
    if destino.exists():
        # evita pisar un clip existente si suben dos archivos con el mismo nombre
        base, ext = os.path.splitext(nombre)
        nombre = f"{base}_{uuid.uuid4().hex[:6]}{ext}"
        destino = REF_VOICES_DIR / nombre

    contenido = await file.read(MAX_BYTES_VOZ + 1)
    if not contenido:
        raise HTTPException(400, "El archivo está vacío")
    if len(contenido) > MAX_BYTES_VOZ:
        raise HTTPException(413, "El clip supera el límite de 20 MB")
    try:
        import io
        with wave.open(io.BytesIO(contenido), "rb") as audio:
            if audio.getnframes() == 0:
                raise ValueError("sin audio")
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(400, "El archivo no es un WAV válido")
    with open(destino, "wb") as f:
        f.write(contenido)
    return {"ok": True, "archivo": nombre}


MAX_CARACTERES_TEXTO = 5000
MAX_BYTES_VOZ = 20 * 1024 * 1024


@app.post("/api/sintetizar")
def sintetizar(req: SintetizarRequest):
    texto = req.texto.strip()
    if not texto:
        raise HTTPException(400, "El texto no puede estar vacío")
    if len(texto) > MAX_CARACTERES_TEXTO:
        raise HTTPException(
            400,
            f"El texto es demasiado largo ({len(texto)} caracteres, máximo "
            f"{MAX_CARACTERES_TEXTO}). Divídelo en partes más cortas.",
        )
    if not req.voces_referencia:
        raise HTTPException(400, "Selecciona al menos un clip de referencia de voz")

    rutas_referencia = []
    for nombre_crudo in req.voces_referencia:
        nombre = nombre_seguro(nombre_crudo)
        ruta = REF_VOICES_DIR / nombre
        if not ruta.exists():
            raise HTTPException(400, f"No existe el clip de referencia: {nombre}")
        rutas_referencia.append(str(ruta))

    try:
        modelo = cargar_modelo_tts()
    except Exception as e:
        raise HTTPException(500, f"No se pudo cargar el modelo XTTS v2: {e}")

    nombre_salida = f"{uuid.uuid4().hex}.wav"
    ruta_salida = OUTPUT_DIR / nombre_salida

    try:
        modelo.tts_to_file(
            text=texto,
            speaker_wav=rutas_referencia,
            language=req.idioma,
            file_path=str(ruta_salida),
            split_sentences=True,
        )
    except Exception as e:
        raise HTTPException(500, f"Error al generar el audio: {e}")

    return {"archivo": nombre_salida}


@app.get("/api/audio/{nombre_archivo}")
def obtener_audio(nombre_archivo: str):
    nombre = nombre_seguro(nombre_archivo)
    if not nombre.lower().endswith(".wav"):
        raise HTTPException(404, "Audio no encontrado")
    ruta = OUTPUT_DIR / nombre
    if not ruta.exists():
        raise HTTPException(404, "Audio no encontrado")
    return FileResponse(ruta, media_type="audio/wav")


# ---------------------------------------------------------------------------
# Frontend estático
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

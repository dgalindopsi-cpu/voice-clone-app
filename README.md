# Clonador de voz local

App web local: escribes texto, Gemini lo reescribe en el tono que elijas, y XTTS v2 lo convierte en audio con tu voz clonada.

## 1. Instalar (Windows, PowerShell)

```powershell
# Python 3.11 recomendado (XTTS aún no soporta bien 3.12+)
python -m venv venv
venv\Scripts\activate

# PyTorch con CUDA (revisa tu versión de CUDA con: nvidia-smi)
pip install torch --index-url https://download.pytorch.org/whl/cu121

pip install -r requirements.txt
```

## 2. Configurar tu API key de Gemini

```powershell
$env:GEMINI_API_KEY = "tu_api_key_aqui"
```

(Para que quede permanente, agrégala como variable de entorno del sistema en Windows en vez de por sesión.)

## 3. Agregar tus clips de voz

Coloca uno o varios archivos `.wav` con tu voz en la carpeta `reference_voices/`.

- Recomendado: 3-5 clips de 10-20 segundos cada uno, audio limpio (sin ruido de fondo ni música), voz clara y con entonación variada.
- También puedes subirlos desde la interfaz web una vez que la app esté corriendo.
- Si tienes un audio largo (varios minutos), córtalo en fragmentos de 10-20 segundos con cualquier editor de audio (Audacity funciona bien) — XTTS v2 usa clips cortos, pero puedes pasarle varios a la vez y promedia el embedding de tu voz para un resultado más fiel.

## 4. Correr la app

```powershell
python main.py
```

Abre `http://127.0.0.1:8000` en el navegador.

En Windows también puedes iniciar la app con `run.bat` después de crear el entorno virtual.

## Privacidad y uso responsable

- Usa únicamente voces propias o de personas que hayan dado su consentimiento para clonarlas.
- Los clips de `reference_voices/`, los audios de `output/`, el entorno virtual y los archivos `.env` están excluidos de Git. No subas grabaciones ni claves al repositorio.
- La app escucha solo en `127.0.0.1`; no está preparada para exponerse directamente a Internet.
- Cada clip subido debe ser un WAV válido de hasta 20 MB.

## Notas

- La primera vez que sintetizas, XTTS v2 descarga los pesos del modelo (~2GB) — puede tardar unos minutos.
- XTTS v2 se distribuye bajo la licencia **CPML** (uso no comercial, gratis para uso personal como este) — el `main.py` ya acepta los términos de forma automática (`COQUI_TOS_AGREED=1`) para que el servidor no se quede colgado esperando una confirmación por consola que nunca puede llegar (así lo pediría por defecto). Detalles: https://coqui.ai/cpml
- Con 4GB de VRAM (RTX 2050) estás justo en el mínimo recomendado para XTTS v2 (4-6GB ideal). La inferencia corre en FP16 y normalmente entra bien, pero si te quedás sin memoria (`CUDA out of memory`), cerrá otras apps que usen GPU o probá con textos más cortos.
- Los tonos se editan directamente en `tonos.json` — puedes agregar tantos como quieras sin tocar el código.
- Los audios generados se guardan en `output/`.
- El texto por síntesis está limitado a 5000 caracteres (ajustable en `main.py`, constante `MAX_CARACTERES_TEXTO`) — es más que suficiente para un mensaje o párrafo, y evita esperas excesivas.

## Solución de problemas

- **El servidor se queda colgado en la primera síntesis y no responde**: si ves en la consola el texto sobre "terms of service" y no avanza, es la licencia CPML pidiendo confirmación interactiva. Con el `main.py` de este proyecto ya no debería pasar, pero si lo modificaste, asegurate de que `COQUI_TOS_AGREED=1` esté seteado antes de importar `TTS`.
- **`CUDA out of memory`**: cerrá otras apps que usen la GPU (navegador con muchas pestañas, otros modelos, juegos). Como alternativa, podés forzar CPU editando `cargar_modelo_tts()` en `main.py` (más lento, pero funciona).
- **Error al instalar `coqui-tts`**: usá Python 3.10-3.13 (evitá 3.14+ hasta que haya wheels). Verificá tu versión con `python --version`.
- **Error de Gemini (401/403)**: revisá que `GEMINI_API_KEY` esté bien seteada en la sesión de PowerShell donde corrés `python main.py`.

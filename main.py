from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Path
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import subprocess
import shutil

app = FastAPI()

# Habilitar CORS para permitir que el frontend acceda a los archivos estáticos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes (puedes ajustarlo según sea necesario)
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los encabezados
)

# Directorios de archivos
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
AUDIVERIS_DIR = "/home/kaval/Documents/audiveris"  # Ajusta esta ruta si es necesario
PUBLIC_MIDI_DIR = os.path.join("static", "midi")
PUBLIC_MXL_DIR = os.path.join("static", "mxl")

# Crear las carpetas necesarias si no existen
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PUBLIC_MIDI_DIR, exist_ok=True)
os.makedirs(PUBLIC_MXL_DIR, exist_ok=True)

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/api/upload")
async def upload(title: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    # Usar el título como nombre base
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    base_filename = f"{safe_title}.pdf"
    upload_path = os.path.join(UPLOAD_DIR, base_filename)

    # Guardar archivo PDF
    with open(upload_path, "wb") as f:
        f.write(await file.read())

    # Ejecutar Audiveris
    command = [
        "./gradlew",
        "run",
        f'--args=-batch -export -output {os.path.abspath(OUTPUT_DIR)} {os.path.abspath(upload_path)}'
    ]
    try:
        subprocess.run(command, cwd=AUDIVERIS_DIR, check=True)
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Error al ejecutar Audiveris.")

    # Rutas de salida
    midi_name = f"{safe_title}.midi"
    xml_name = f"{safe_title}.mxl"
    midi_path = os.path.join(OUTPUT_DIR, midi_name)
    xml_path = os.path.join(OUTPUT_DIR, xml_name)

    # Convertir XML a MIDI usando MuseScore
    if not os.path.exists(midi_path) and os.path.exists(xml_path):
        try:
            subprocess.run(["mscore", xml_path, "-o", midi_path], check=True)
        except FileNotFoundError:
            try:
                subprocess.run(["musescore", xml_path, "-o", midi_path], check=True)
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="MuseScore no está instalado o no se pudo ejecutar.")

    # Verificar y mover archivos
    result = {}
    if os.path.exists(midi_path):
        public_midi_path = os.path.join(PUBLIC_MIDI_DIR, midi_name)
        shutil.move(midi_path, public_midi_path)
        result["midi_url"] = f"/static/midi/{midi_name}"
    else:
        result["midi_url"] = None

    if os.path.exists(xml_path):
        public_mxl_path = os.path.join(PUBLIC_MXL_DIR, xml_name)
        shutil.move(xml_path, public_mxl_path)
        result["mxl_url"] = f"/static/mxl/{xml_name}"
    else:
        result["mxl_url"] = None

    if not result["midi_url"] and not result["mxl_url"]:
        raise HTTPException(status_code=500, detail="No se pudieron generar los archivos MIDI ni MXL.")

    return JSONResponse(content=result)

@app.get("/api/search/{title}")
async def search_files(title: str = Path(..., description="Título del archivo a buscar")):
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()

    midi_filename = f"{safe_title}.midi"
    xml_filename = f"{safe_title}.mxl"

    midi_path = os.path.join(PUBLIC_MIDI_DIR, midi_filename)
    xml_path = os.path.join(PUBLIC_MXL_DIR, xml_filename)

    result = {
        "title": title,
        "midi_exists": os.path.exists(midi_path),
        "mxl_exists": os.path.exists(xml_path),
        "midi_url": f"/static/midi/{midi_filename}" if os.path.exists(midi_path) else None,
        "mxl_url": f"/static/mxl/{xml_filename}" if os.path.exists(xml_path) else None
    }

    return JSONResponse(content=result)

# Manejar solicitudes OPTIONS para la verificación de CORS (pre-flight)
@app.options("/static/{file_path:path}")
async def handle_options(file_path: str):
    return JSONResponse(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
    )

import os
import shutil
import uuid

# ✅ CAMBIO: quitamos "from ast import List"
# ✅ CAMBIO: usamos List desde typing
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.multimedia import Evidencia
from app.models.operaciones import Incidente

from app.ia.audio_service import transcribir_audio
from app.ia.imagen_service import analizar_imagen
from app.ia.fusion_service import fusionar_resultados

router = APIRouter(prefix="/evidencias", tags=["Evidencias"])

UPLOAD_DIR = "uploads"
UPLOAD_IMG_DIR = f"{UPLOAD_DIR}/imagenes"
UPLOAD_AUDIO_DIR = f"{UPLOAD_DIR}/audios"

os.makedirs(UPLOAD_IMG_DIR, exist_ok=True)
os.makedirs(UPLOAD_AUDIO_DIR, exist_ok=True)


# Guarda un archivo subido en el sistema de archivos con nombre único
# Caso de uso: Almacenamiento de evidencias multimedia
def guardar_archivo(archivo: UploadFile, carpeta: str, extension_default: str) -> str:
    ext = os.path.splitext(archivo.filename or "")[1]

    if not ext:
        ext = extension_default

    nombre = f"{uuid.uuid4()}{ext}"
    ruta = os.path.join(carpeta, nombre)

    with open(ruta, "wb") as f:
        shutil.copyfileobj(archivo.file, f)

    return ruta


# ============================================================
# SUBIR MUCHAS IMÁGENES
# ============================================================
# Sube una o múltiples imágenes de un incidente y las analiza con IA
# Caso de uso: CU-11 + CU-12 + CU-13 Subir y analizar imágenes de evidencia
@router.post("/imagen/{id_incidente}")
async def subir_imagenes(
    id_incidente: int,
    archivo: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    CU11 + CU12 + CU13:
    Sube una o muchas imágenes y las analiza con IA.
    """

    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    evidencias_guardadas = []
    analisis_guardados = []

    # ✅ CAMBIO: recorremos cada imagen
    for img in archivo:
        if not img.content_type or not img.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {img.filename} no es una imagen válida"
            )

        # ✅ CAMBIO: guardamos una imagen por vuelta
        ruta = guardar_archivo(img, UPLOAD_IMG_DIR, ".jpg")

        # ✅ CAMBIO: analizamos cada imagen
        analisis = analizar_imagen(ruta)

        evidencia = Evidencia(
            url_archivo=ruta,
            id_tipo_evidencia=1,  # 1 = Imagen
            id_incidente=id_incidente,

            # ✅ CAMBIO:
            # Si tu IA devuelve descripcion, usamos descripcion.
            # Si devuelve transcripcion, usamos transcripcion.
            transcripcion=analisis.get("descripcion")
            or analisis.get("transcripcion")
            or ""
        )

        db.add(evidencia)
        evidencias_guardadas.append(evidencia)
        analisis_guardados.append(analisis)

    db.commit()

    for evidencia in evidencias_guardadas:
        db.refresh(evidencia)

    return {
        "mensaje": "Imágenes subidas y analizadas correctamente",
        "total": len(evidencias_guardadas),
        "evidencias": [
            {
                "codigo": e.codigo,
                "url_archivo": e.url_archivo,
                "id_tipo_evidencia": e.id_tipo_evidencia,
                "id_incidente": e.id_incidente,
                "transcripcion": e.transcripcion,
            }
            for e in evidencias_guardadas
        ],
        "analisis_ia": analisis_guardados
    }


# ============================================================
# SUBIR MUCHOS AUDIOS
# ============================================================

# ✅ CAMBIO:
# Antes tenías "/audio/{id_cliente}", pero la función recibe id_incidente.
# Lo correcto es "/audio/{id_incidente}".
# Sube uno o múltiples audios de un incidente y los transcribe con IA
# Caso de uso: CU-11 + CU-12 + CU-13 Subir y transcribir audios de evidencia
@router.post("/audio/{id_incidente}")
async def subir_audios(
    id_incidente: int,
    archivo: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    CU11 + CU12 + CU13:
    Sube uno o muchos audios y los transcribe con IA.
    """

    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    evidencias_guardadas = []
    resultados_guardados = []

    # ✅ CAMBIO: recorremos cada audio
    for audio in archivo:
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {audio.filename} no es un audio válido"
            )

        ruta = guardar_archivo(audio, UPLOAD_AUDIO_DIR, ".m4a")

        resultado = transcribir_audio(ruta)

        evidencia = Evidencia(
            url_archivo=ruta,
            id_tipo_evidencia=2,  # 2 = Audio
            id_incidente=id_incidente,
            transcripcion=resultado.get("transcripcion", "")
        )

        db.add(evidencia)
        evidencias_guardadas.append(evidencia)
        resultados_guardados.append(resultado)

    db.commit()

    for evidencia in evidencias_guardadas:
        db.refresh(evidencia)

    return {
        "mensaje": "Audios subidos y analizados correctamente",
        "total": len(evidencias_guardadas),
        "evidencias": [
            {
                "codigo": e.codigo,
                "url_archivo": e.url_archivo,
                "id_tipo_evidencia": e.id_tipo_evidencia,
                "id_incidente": e.id_incidente,
                "transcripcion": e.transcripcion,
            }
            for e in evidencias_guardadas
        ],
        "resultados_audio": resultados_guardados
    }


# ============================================================
# SUBIR TEXTO
# ============================================================
# Guarda una descripción de texto como evidencia del incidente
# Caso de uso: CU-11 Guardar descripción textual de evidencia
@router.post("/texto/{id_incidente}")
async def subir_texto(
    id_incidente: int,
    descripcion: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    CU11:
    Guarda descripción de texto.
    """

    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    evidencia = Evidencia(
        # ✅ OJO:
        # Si tu columna url_archivo NO permite NULL, cambia None por "SIN_ARCHIVO"
        url_archivo=None,
        id_tipo_evidencia=3,  # 3 = Texto
        id_incidente=id_incidente,
        transcripcion=descripcion
    )

    db.add(evidencia)
    db.commit()
    db.refresh(evidencia)

    return {
        "mensaje": "Descripción guardada correctamente",
        "evidencia": {
            "codigo": evidencia.codigo,
            "url_archivo": evidencia.url_archivo,
            "id_tipo_evidencia": evidencia.id_tipo_evidencia,
            "id_incidente": evidencia.id_incidente,
            "transcripcion": evidencia.transcripcion,
        }
    }


# ============================================================
# ENDPOINT GENERAL: IMÁGENES + AUDIOS + TEXTO EN UNA SOLA PETICIÓN
# ============================================================
# Sube múltiples imágenes, audios y texto en una sola petición
# Caso de uso: CU-11 + CU-12 + CU-13 Subir evidencias multimedia combinadas
@router.post("/multimedia/{id_incidente}")
async def subir_multimedia(
    id_incidente: int,
    imagenes: Optional[List[UploadFile]] = File(None),
    audios: Optional[List[UploadFile]] = File(None),
    texto: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Sube varias imágenes, varios audios y texto en una sola petición.
    """

    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente
    ).first()

    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    imagenes = imagenes or []
    audios = audios or []

    if not imagenes and not audios and not texto:
        raise HTTPException(
            status_code=400,
            detail="Debe enviar al menos una imagen, un audio o un texto"
        )

    evidencias_guardadas = []
    resultados_ia = {
        "imagenes": [],
        "audios": [],
        "texto": texto
    }

    # ✅ CAMBIO: procesar muchas imágenes
    for img in imagenes:
        if not img.content_type or not img.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {img.filename} no es una imagen válida"
            )

        ruta = guardar_archivo(img, UPLOAD_IMG_DIR, ".jpg")
        analisis = analizar_imagen(ruta)

        evidencia = Evidencia(
            url_archivo=ruta,
            id_tipo_evidencia=1,
            id_incidente=id_incidente,
            transcripcion=analisis.get("descripcion")
            or analisis.get("transcripcion")
            or ""
        )

        db.add(evidencia)
        evidencias_guardadas.append(evidencia)
        resultados_ia["imagenes"].append(analisis)

    # ✅ CAMBIO: procesar muchos audios
    for audio in audios:
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=400,
                detail=f"El archivo {audio.filename} no es un audio válido"
            )

        ruta = guardar_archivo(audio, UPLOAD_AUDIO_DIR, ".m4a")
        resultado = transcribir_audio(ruta)

        evidencia = Evidencia(
            url_archivo=ruta,
            id_tipo_evidencia=2,
            id_incidente=id_incidente,
            transcripcion=resultado.get("transcripcion", "")
        )

        db.add(evidencia)
        evidencias_guardadas.append(evidencia)
        resultados_ia["audios"].append(resultado)

    # ✅ CAMBIO: guardar texto
    if texto and texto.strip():
        evidencia_texto = Evidencia(
            # Si url_archivo no permite NULL, usa "SIN_ARCHIVO"
            url_archivo=None,
            id_tipo_evidencia=3,
            id_incidente=id_incidente,
            transcripcion=texto.strip()
        )

        db.add(evidencia_texto)
        evidencias_guardadas.append(evidencia_texto)

    # ✅ CAMBIO OPCIONAL:
    # Si tu fusion_service está bien implementado, puedes fusionar resultados.
    # Si te da error, comenta estas líneas.
    try:
        fusion = fusionar_resultados(resultados_ia)
    except Exception as e:
        fusion = {
            "mensaje": "No se pudo fusionar resultados",
            "error": str(e)
        }

    db.commit()

    for evidencia in evidencias_guardadas:
        db.refresh(evidencia)

    return {
        "mensaje": "Evidencias multimedia registradas correctamente",
        "total": len(evidencias_guardadas),
        "evidencias": [
            {
                "codigo": e.codigo,
                "url_archivo": e.url_archivo,
                "id_tipo_evidencia": e.id_tipo_evidencia,
                "id_incidente": e.id_incidente,
                "transcripcion": e.transcripcion,
            }
            for e in evidencias_guardadas
        ],
        "resultado_fusion": fusion
    }


# ============================================================
# LISTAR EVIDENCIAS DE UN INCIDENTE
# ============================================================
# Lista todas las evidencias asociadas a un incidente
# Caso de uso: Consulta de evidencias por incidente
@router.get("/{id_incidente}")
def listar_evidencias(id_incidente: int, db: Session = Depends(get_db)):
    """
    Lista todas las evidencias de un incidente.
    """

    evidencias = db.query(Evidencia).filter(
        Evidencia.id_incidente == id_incidente
    ).all()

    return [
        {
            "codigo": e.codigo,
            "url_archivo": e.url_archivo,
            "transcripcion": e.transcripcion,
            "id_tipo_evidencia": e.id_tipo_evidencia,
            "fecha_subida": e.fecha_subida
        }
        for e in evidencias
    ]
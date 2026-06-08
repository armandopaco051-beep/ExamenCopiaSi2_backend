from fastapi import APIRouter ,Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.operaciones import Incidente
from app.models.multimedia import Evidencia
from app.ia.fusion_service import fusionar_resultados
from app.ia.texto_service import clasificar_texto
from app.ia.imagen_service import analizar_imagen
from app.ia.audio_service import transcribir_audio
from pydantic import BaseModel
from fastapi import HTTPException

#hacemos los endpoints para la ia

router = APIRouter(prefix="/ia", tags=["IA"])

class TextoRequest(BaseModel): 
    texto: str 

# Clasifica un texto de incidente para determinar categoría y prioridad
# Caso de uso: CU-12 Clasificación de texto con IA
@router.post("/clasificar")
def clasificar(texto: TextoRequest):
    #Cu12 clasifica texto del incidente 
    return clasificar_texto(texto.texto)

# Procesa todas las evidencias de un incidente y genera ficha técnica con IA
# Caso de uso: CU-12 + CU-13 + CU-14 + CU-15 Procesamiento completo de incidente con IA
@router.post("/procesar-incidente/{id_incidente}")
def procesar_incidente_completo(
    id_incidente: int ,
    db: Session = Depends(get_db)
):
 # CU12 + CU13 + CU14 + CU15 Procesa todas las evidencia de un incidente y generaficha tecnica 
    incidente = db.query(Incidente).filter(Incidente.codigo == id_incidente).first()
    if not incidente :
        raise HTTPException(status_code=404, detail="Incidente no encontrado")
    evidencias = db.query(Evidencia).filter(
        Evidencia.id_incidente == id_incidente).all()

    resultado_audio = None
    resultado_imagen = None
    descripcion_texto = incidente.descripcion or ""

    for ev in evidencias:
        if ev.id_tipo_evidencia == 1 and ev.url_archivo:
            # Imagen
            resultado_imagen = analizar_imagen(ev.url_archivo)

        elif ev.id_tipo_evidencia == 2 and ev.url_archivo:
            # Audio — usar transcripción guardada o re-transcribir
            if ev.transcripcion:
                resultado_audio = {
                    "ok": True,
                    "transcripcion": ev.transcripcion,
                    "palabras_clave": []
                }
            else:
                resultado_audio = transcribir_audio(ev.url_archivo)
                ev.transcripcion = resultado_audio.get("transcripcion", "")

        elif ev.id_tipo_evidencia == 3 and ev.transcripcion:
            # Texto
            descripcion_texto = ev.transcripcion

    # Fusionar todos los resultados
    fusion = fusionar_resultados(
        resultado_audio=resultado_audio,
        resultado_imagen=resultado_imagen,
        resultado_texto=None,
        descripcion_manual=descripcion_texto
    )

    # Actualizar incidente con resultados de IA
    incidente.id_categoria_problema = fusion["id_categoria"]
    incidente.id_prioridad = fusion["id_prioridad"]
    db.commit()

    return {
        "id_incidente": id_incidente,
        "categoria": fusion["categoria_final"],
        "id_categoria": fusion["id_categoria"],
        "prioridad": fusion["id_prioridad"],
        "confianza": fusion["confianza"],
        "requiere_revision": fusion["requiere_revision"],
        "ficha_tecnica": fusion["resumen"],
        "analisis_detallado": {
            "imagen": resultado_imagen,
            "audio": resultado_audio,
            "votos": fusion["votos"]
        }
    }


# Obtiene la ficha técnica procesada del incidente
# Caso de uso: CU-15 Obtener ficha técnica de incidente
@router.get("/ficha/{id_incidente}")
def obtener_ficha(id_incidente: int, db: Session = Depends(get_db)):
    """CU-15: Obtiene la ficha técnica procesada del incidente"""
    incidente = db.query(Incidente).filter(
        Incidente.codigo == id_incidente).first()
    if not incidente:
        raise HTTPException(status_code=404, detail="Incidente no encontrado")

    evidencias = db.query(Evidencia).filter(
        Evidencia.id_incidente == id_incidente).all()

    transcripciones = [e.transcripcion for e in evidencias
                       if e.transcripcion]
    imagenes = [e.url_archivo for e in evidencias
                if e.id_tipo_evidencia == 1 and e.url_archivo]

    return {
        "id_incidente": id_incidente,
        "descripcion": incidente.descripcion,
        "id_categoria": incidente.id_categoria_problema,
        "id_prioridad": incidente.id_prioridad,
        "latitud": float(incidente.latitud),
        "longitud": float(incidente.longitud),
        "fecha_reporte": incidente.fecha_reporte,
        "transcripciones": transcripciones,
        "cantidad_imagenes": len(imagenes),
        "estado": incidente.id_estado_incidente
    }



from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.seguridad import Usuario
from app.models.talleres import Taller
from app.services.auth_service import hash_password, registrar_bitacora


router = APIRouter(prefix="/chatbot/landing", tags=["Chatbot Landing"])


PLATAFORMA_INFO = {
    "nombre": "Plataforma Inteligente de Emergencias Vehiculares",
    "descripcion": (
        "Conectamos clientes con talleres y tecnicos cercanos para atender "
        "emergencias vehiculares, gestionar cotizaciones, seguimiento, pagos "
        "y evaluaciones del servicio."
    ),
    "beneficios_taller": [
        "Recibir solicitudes de emergencia de clientes cercanos.",
        "Administrar tecnicos, asignaciones y disponibilidad.",
        "Enviar cotizaciones y registrar pagos de servicios.",
        "Consultar historial de clientes atendidos.",
        "Medir evaluaciones y reputacion del taller."
    ],
    "requisitos_taller": [
        "Datos del encargado: CI, nombre, apellido, correo, telefono y password.",
        "Datos del taller: nombre comercial, telefono y direccion.",
        "Ubicacion aproximada: latitud y longitud.",
        "Horario de atencion.",
        "Tecnicos disponibles para atender solicitudes."
    ],
    "procedimiento_solicitudes": {
        "cliente_envia_solicitud": [
            "El cliente inicia sesion o se registra en la plataforma.",
            "Registra o selecciona su vehiculo.",
            "Reporta el incidente indicando descripcion, ubicacion y evidencias si corresponde.",
            "El sistema clasifica el problema y calcula prioridad.",
            "La plataforma busca talleres cercanos dentro de cobertura o permite solicitar cotizaciones.",
            "El cliente espera la aceptacion del taller y la asignacion de un tecnico.",
            "Luego puede ver seguimiento, chat, pago, comprobante y evaluacion."
        ],
        "taller_recibe_solicitud": [
            "El taller primero envia su solicitud de registro desde el landing o desde el formulario.",
            "El administrador revisa y aprueba el taller.",
            "El admin_taller inicia sesion y registra sus tecnicos.",
            "Cuando un cliente reporta una emergencia cercana, el sistema envia la solicitud al taller segun ubicacion, cobertura y disponibilidad.",
            "El admin_taller acepta o rechaza la solicitud.",
            "Si acepta, asigna un tecnico disponible.",
            "El tecnico atiende el servicio y actualiza el estado.",
            "El taller puede consultar historial, pagos, evaluaciones y clientes atendidos."
        ],
        "reglas": [
            "Cada admin_taller solo ve informacion de su propio taller.",
            "Cada cliente solo ve sus propios incidentes y servicios.",
            "Las solicitudes pueden manejarse por asignacion directa o por cotizacion.",
            "Las notificaciones informan cambios importantes al cliente y al taller."
        ]
    },
    "planes": [
        {
            "codigo": "gratis",
            "nombre": "Plan Inicial",
            "precio_mensual_bs": 0,
            "descripcion": "Plan de prueba para registrar el taller y empezar a operar.",
            "incluye": [
                "Registro del taller",
                "Gestion basica de tecnicos",
                "Recepcion de solicitudes",
                "Historial de servicios"
            ]
        },
        {
            "codigo": "estandar",
            "nombre": "Plan Estandar",
            "precio_mensual_bs": 99,
            "descripcion": "Plan simulado para talleres con mayor volumen operativo.",
            "incluye": [
                "Mas tecnicos",
                "Reportes administrativos",
                "Cotizaciones avanzadas",
                "Soporte prioritario"
            ]
        }
    ]
}


INTENCIONES = {
    "saludo": ["hola", "buenas", "buen dia", "buenas tardes", "buenas noches"],
    "como_funciona": ["como funciona", "funciona", "plataforma", "sistema", "emergencias"],
    "procedimiento_solicitudes": [
        "como recibo solicitudes",
        "recibo solicitudes",
        "enviar solicitudes",
        "como envio solicitudes",
        "como se envia una solicitud",
        "procedimiento",
        "flujo de solicitud",
        "solicitudes de emergencia",
        "como llega una solicitud"
    ],
    "planes_suscripciones": ["plan", "planes", "precio", "costo", "suscripcion", "suscripciones", "mensualidad"],
    "requisitos_taller": ["requisito", "necesito", "documento", "datos", "registrar taller", "registro"],
    "beneficios_taller": ["beneficio", "ventaja", "ganar", "clientes", "por que"],
    "registrar_taller": ["quiero registrarme", "solicitar registro", "registrarme", "inscribir", "crear taller"],
    "tecnicos": ["tecnico", "tecnicos", "mecanico", "disponibilidad"],
    "pagos": ["pago", "pagos", "cobro", "cobrar", "comprobante"],
    "contacto": ["contacto", "administrador", "asesor", "llamen", "whatsapp"],
    "despedida": ["gracias", "chau", "adios", "hasta luego"]
}


class ChatbotMensajeRequest(BaseModel):
    mensaje: str = Field(min_length=1)
    contexto: Optional[dict] = None


class ChatbotAccion(BaseModel):
    tipo: str
    label: str
    payload: Optional[dict] = None


class ChatbotMensajeResponse(BaseModel):
    respuesta: str
    intencion: str
    confianza: float
    acciones: list[ChatbotAccion]
    datos: Optional[dict] = None


class SolicitudTallerChatbotRequest(BaseModel):
    codigo_usuario: str
    nombre: str
    apellido: str
    email: EmailStr
    password: str
    telefono: str
    nombre_taller: str
    telefono_taller: str
    direccion_taller: str
    latitud_taller: Decimal
    longitud_taller: Decimal
    horario_inicio: Optional[time] = time(8, 0)
    horario_fin: Optional[time] = time(18, 0)
    origen: str = "chatbot_landing"


def normalizar(texto: str) -> str:
    return (texto or "").strip().lower()


def detectar_intencion(mensaje: str):
    texto = normalizar(mensaje)
    mejor_intencion = "fallback"
    mejor_score = 0

    for intencion, claves in INTENCIONES.items():
        score = sum(1 for clave in claves if clave in texto)
        if score > mejor_score:
            mejor_score = score
            mejor_intencion = intencion

    confianza = min(1.0, 0.35 + (mejor_score * 0.25)) if mejor_score else 0.2
    return mejor_intencion, round(confianza, 2)


def acciones_base():
    return [
        ChatbotAccion(tipo="ver_planes", label="Ver planes"),
        ChatbotAccion(tipo="ver_requisitos", label="Ver requisitos"),
        ChatbotAccion(tipo="iniciar_solicitud_taller", label="Registrar mi taller")
    ]


def construir_respuesta(intencion: str, confianza: float) -> ChatbotMensajeResponse:
    if intencion == "saludo":
        return ChatbotMensajeResponse(
            respuesta=(
                "Hola, soy el asistente de la plataforma. Puedo explicarte como funciona, "
                "mostrar planes, requisitos o ayudarte a solicitar el registro de tu taller."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=acciones_base(),
            datos={"plataforma": PLATAFORMA_INFO["nombre"]}
        )

    if intencion == "como_funciona":
        return ChatbotMensajeResponse(
            respuesta=PLATAFORMA_INFO["descripcion"],
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="ver_beneficios", label="Beneficios para talleres"),
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Solicitar registro")
            ],
            datos={"beneficios_taller": PLATAFORMA_INFO["beneficios_taller"]}
        )

    if intencion == "procedimiento_solicitudes":
        return ChatbotMensajeResponse(
            respuesta=(
                "El procedimiento de la plataforma empieza cuando el cliente reporta un incidente "
                "con ubicacion y descripcion. El sistema clasifica la emergencia, busca talleres "
                "cercanos dentro de cobertura, envia la solicitud al taller, el admin_taller acepta "
                "o rechaza, asigna un tecnico y el cliente puede hacer seguimiento hasta el pago "
                "y la evaluacion."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="ver_requisitos", label="Requisitos para taller"),
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Registrar mi taller"),
                ChatbotAccion(tipo="ver_planes", label="Ver suscripciones")
            ],
            datos=PLATAFORMA_INFO["procedimiento_solicitudes"]
        )

    if intencion == "planes_suscripciones":
        return ChatbotMensajeResponse(
            respuesta=(
                "Tenemos planes simulados para el landing. Puedes iniciar gratis y luego "
                "pasar a un plan estandar con mas reportes y capacidad operativa."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Quiero registrar mi taller"),
                ChatbotAccion(tipo="ver_requisitos", label="Que necesito")
            ],
            datos={"planes": PLATAFORMA_INFO["planes"]}
        )

    if intencion == "requisitos_taller":
        return ChatbotMensajeResponse(
            respuesta=(
                "Para registrar tu taller necesito datos del encargado, datos del taller, "
                "ubicacion, horario de atencion y tecnicos disponibles."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Completar solicitud"),
                ChatbotAccion(tipo="ver_planes", label="Ver suscripciones")
            ],
            datos={"requisitos": PLATAFORMA_INFO["requisitos_taller"]}
        )

    if intencion == "beneficios_taller":
        return ChatbotMensajeResponse(
            respuesta=(
                "El taller puede recibir mas solicitudes, organizar tecnicos, cotizar servicios "
                "y consultar su historial de clientes atendidos."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="ver_planes", label="Ver planes"),
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Registrarme")
            ],
            datos={"beneficios": PLATAFORMA_INFO["beneficios_taller"]}
        )

    if intencion == "registrar_taller":
        return ChatbotMensajeResponse(
            respuesta=(
                "Perfecto. Te guiare con la solicitud. Necesito los datos del encargado "
                "y los datos del taller para enviarlos al administrador."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(
                    tipo="abrir_formulario_solicitud_taller",
                    label="Abrir formulario",
                    payload={"endpoint": "/chatbot/landing/solicitud-taller"}
                )
            ],
            datos={"campos_requeridos": list(SolicitudTallerChatbotRequest.model_fields.keys())}
        )

    if intencion == "tecnicos":
        return ChatbotMensajeResponse(
            respuesta=(
                "Cada taller puede registrar tecnicos, controlar disponibilidad y asignarlos "
                "a solicitudes aceptadas."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=acciones_base(),
            datos=None
        )

    if intencion == "pagos":
        return ChatbotMensajeResponse(
            respuesta=(
                "La plataforma permite registrar cobros por servicio, pagos y comprobantes. "
                "Los pagos de suscripcion pueden integrarse con Stripe."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=acciones_base(),
            datos=None
        )

    if intencion == "contacto":
        return ChatbotMensajeResponse(
            respuesta=(
                "Puedo derivarte con el administrador. Tambien puedes dejar una solicitud "
                "de registro para que revisen tu taller."
            ),
            intencion=intencion,
            confianza=confianza,
            acciones=[
                ChatbotAccion(tipo="contactar_admin", label="Contactar administrador"),
                ChatbotAccion(tipo="iniciar_solicitud_taller", label="Enviar solicitud")
            ],
            datos={"contacto_simulado": {"canal": "WhatsApp", "telefono": "+591 70000000"}}
        )

    if intencion == "despedida":
        return ChatbotMensajeResponse(
            respuesta="Gracias por visitar la plataforma. Cuando quieras, puedo ayudarte a registrar tu taller.",
            intencion=intencion,
            confianza=confianza,
            acciones=[],
            datos=None
        )

    return ChatbotMensajeResponse(
        respuesta=(
            "Puedo ayudarte con informacion sobre planes, requisitos, funcionamiento "
            "o registro de talleres. Que te gustaria consultar?"
        ),
        intencion="fallback",
        confianza=confianza,
        acciones=acciones_base(),
        datos={"sugerencias": list(INTENCIONES.keys())}
    )


@router.get("/contexto")
def obtener_contexto_chatbot():
    return PLATAFORMA_INFO


@router.get("/preguntas-frecuentes")
def preguntas_frecuentes_chatbot():
    return {
        "preguntas": [
            {
                "pregunta": "Como funciona la plataforma?",
                "respuesta": PLATAFORMA_INFO["descripcion"]
            },
            {
                "pregunta": "Que necesito para registrar mi taller?",
                "respuesta": "Necesitas datos del encargado, datos del taller, ubicacion y horario."
            },
            {
                "pregunta": "Tiene costo?",
                "respuesta": "La simulacion incluye un plan inicial gratis y un plan estandar de pago."
            },
            {
                "pregunta": "Como recibo solicitudes?",
                "respuesta": (
                    "Primero el taller envia su solicitud de registro y espera aprobacion. "
                    "Luego registra tecnicos. Cuando un cliente reporta una emergencia, "
                    "el sistema busca talleres cercanos dentro de cobertura y envia la solicitud. "
                    "El admin_taller acepta o rechaza, asigna tecnico y atiende el servicio."
                ),
                "procedimiento": PLATAFORMA_INFO["procedimiento_solicitudes"]["taller_recibe_solicitud"]
            },
            {
                "pregunta": "Como envia una solicitud el cliente?",
                "respuesta": (
                    "El cliente registra su vehiculo, reporta el incidente con ubicacion y evidencias, "
                    "y la plataforma deriva la solicitud a talleres cercanos o a un flujo de cotizacion."
                ),
                "procedimiento": PLATAFORMA_INFO["procedimiento_solicitudes"]["cliente_envia_solicitud"]
            }
        ]
    }


@router.post("/mensaje", response_model=ChatbotMensajeResponse)
def responder_mensaje_chatbot(datos: ChatbotMensajeRequest):
    intencion, confianza = detectar_intencion(datos.mensaje)
    return construir_respuesta(intencion, confianza)


@router.post("/solicitud-taller", status_code=201)
def crear_solicitud_taller_desde_chatbot(
    datos: SolicitudTallerChatbotRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    if db.query(Usuario).filter(Usuario.codigo == datos.codigo_usuario).first():
        raise HTTPException(status_code=400, detail="El CI ya esta registrado")

    if db.query(Usuario).filter(Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="El email ya esta registrado")

    nuevo_usuario = Usuario(
        codigo=datos.codigo_usuario,
        nombre=datos.nombre,
        apellido=datos.apellido,
        email=datos.email,
        password=hash_password(datos.password),
        telefono=datos.telefono,
        id_rol=2,
        estado=False,
        estado_registro="pendiente",
        observacion_admin=f"Solicitud generada desde {datos.origen}",
        fecha_registro=datetime.now(),
        fecha_solicitud=datetime.now()
    )
    db.add(nuevo_usuario)
    db.flush()

    nuevo_taller = Taller(
        nombre=datos.nombre_taller,
        telefono=datos.telefono_taller,
        direccion=datos.direccion_taller,
        latitud=float(datos.latitud_taller),
        longitud=float(datos.longitud_taller),
        horario_inicio=datos.horario_inicio,
        horario_fin=datos.horario_fin,
        activo=False,
        estado_registro="pendiente",
        observacion_admin=f"Solicitud generada desde {datos.origen}",
        fecha_solicitud=datetime.now(),
        usuario_id=datos.codigo_usuario
    )
    db.add(nuevo_taller)
    db.flush()

    registrar_bitacora(
        db=db,
        codigo_usuario=datos.codigo_usuario,
        accion="SOLICITUD_REGISTRO_TALLER_CHATBOT",
        modulo="CHATBOT_LANDING",
        descripcion=f"Solicitud de registro desde chatbot para el taller {datos.nombre_taller}",
        ip_address=request.client.host if request.client else None,
        id_taller=nuevo_taller.codigo
    )

    db.commit()
    db.refresh(nuevo_taller)

    return {
        "mensaje": "Solicitud enviada. El administrador revisara la informacion del taller.",
        "estado_registro": "pendiente",
        "codigo_usuario": datos.codigo_usuario,
        "codigo_taller": nuevo_taller.codigo,
        "siguiente_paso": "Esperar aprobacion del administrador"
    }

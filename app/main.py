#from sys import prefix
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from fastapi.staticfiles import StaticFiles
from app.routers import auth, usuarios, vehiculos, talleres, tecnicos,incidentes, bitacora,evidencias,ia,asignacion,dashboard,solicitudes, tracking, validacion_arribo, chat, pagos, evaluaciones, notificaciones, suscripciones, cotizaciones, sync, chatbot_landing
import os 


app = FastAPI(
    title=settings.app_name,
    description="Backend - Plataforma Inteligente de Emergencias Vehiculares | Ciclo 1",
    version="1.0.0",
    redirect_slashes=False  # ✅ ESTO EVITA EL 307    
)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://examen-copia-si2-frontend.vercel.app",
        "http://localhost:4200",
        "http://127.0.0.1:4200",
      #  "https://examencopiasi2-backend.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar todos los routers del Ciclo 1
app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(usuarios.roles_router)
app.include_router(usuarios.permisos_router)
app.include_router(vehiculos.router)
app.include_router(talleres.router)
app.include_router(tecnicos.router)
app.include_router(incidentes.router)
app.include_router(bitacora.router)
app.include_router(evidencias.router)
app.include_router(ia.router)
app.include_router(asignacion.router)
app.include_router(dashboard.router)
app.include_router(solicitudes.router)
app.include_router(tracking.router)
app.include_router(validacion_arribo.router)
app.include_router(chat.router)
app.include_router(chatbot_landing.router)
app.include_router(pagos.router)
app.include_router(evaluaciones.router)
app.include_router(notificaciones.router)
app.include_router(suscripciones.router)
app.include_router(cotizaciones.router)
app.include_router(sync.router)
app.include_router(incidentes.router , prefix = "/incidentes",  tags=["Incidentes"])

os.makedirs("uploads/imagenes", exist_ok=True)
os.makedirs("uploads/audios", exist_ok=True)

#app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/", tags=["Root"])
def root():
    return {
        "sistema": settings.app_name,
        "ciclo": "Ciclo 1 — CU01 al CU10",
        "docs": "/docs",
        "estado": "✅ Backend corriendo"
    }

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "Backend funcionando correctamente"}


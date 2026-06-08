# Guia de defensa - ubicacion de casos de uso

Este archivo sirve como comentario general del backend para explicar en la defensa donde esta cada caso de uso, que endpoint lo llama y que responsabilidad tiene cada carpeta.

## 1. Estructura principal del backend

```txt
app/
  main.py
  config.py
  database.py
  models/
  schemas/
  routers/
  services/
  ia/
  utils/

migrations/
uploads/
requirements.txt
.env
```

## 2. Que hace cada carpeta

### app/main.py

Es el punto de entrada del backend FastAPI.

Aqui se registran todos los routers:

```txt
auth
usuarios
vehiculos
talleres
tecnicos
incidentes
evidencias
asignacion
tracking
notificaciones
suscripciones
cotizaciones
sync
pagos
evaluaciones
chat
dashboard
solicitudes
validacion_arribo
```

Cuando el frontend llama un endpoint, primero entra por `main.py`, luego pasa al router correspondiente.

Ejemplo:

```txt
POST /sync/incidentes
entra por main.py
va a app/routers/sync.py
usa schemas de app/schemas/sync.py
guarda datos usando models de app/models/operaciones.py
```

### app/config.py

Centraliza las variables del `.env`.

Aqui estan configuraciones como:

```txt
DATABASE_URL
SECRET_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_SUCCESS_URL
STRIPE_CANCEL_URL
```

Caso de uso relacionado:

```txt
CU: Procesar suscripcion con Stripe
```

### app/database.py

Configura la conexion con la base de datos principal.

Responsabilidad:

```txt
Crear engine SQLAlchemy
Crear SessionLocal
Entregar db con Depends(get_db)
```

Se usa en casi todos los routers.

### app/models/

Contiene las tablas de la base de datos representadas como clases SQLAlchemy.

Ejemplos:

```txt
seguridad.py       -> Usuario, Rol, Permisos
talleres.py        -> Taller, Tecnico, Vehiculo
operaciones.py     -> Incidente, Asignacion, Historial, ConflictoSincronizacion
multimedia.py      -> Evidencia
notificaciones.py  -> Notificacion
suscripciones.py   -> Tenant, PlanSuscripcion, SuscripcionTenant, PagoSuscripcion
```

En defensa puedes decir:

```txt
Los models son el mapa entre Python y las tablas de PostgreSQL.
```

### app/schemas/

Contiene los DTO o estructuras JSON que recibe y responde la API.

Ejemplos:

```txt
incidente.py       -> JSON para crear incidente online/offline
sync.py            -> JSON para sincronizacion offline
suscripciones.py   -> JSON de tenant, plan, pagos y checkout
cotizaciones.py    -> JSON de flujo de cotizacion
```

En defensa puedes decir:

```txt
Los schemas validan los datos que entran desde el frontend antes de llegar a la base de datos.
```

### app/routers/

Contiene los endpoints.

Cada archivo representa un modulo o caso de uso.

Ejemplo:

```txt
app/routers/incidentes.py
```

Contiene endpoints como:

```txt
POST /incidentes
GET /incidentes
PUT /incidentes/{id}
POST /incidentes/sincronizar-offline
```

### app/services/

Contiene logica reutilizable o reglas de negocio.

Ejemplos:

```txt
suscripciones_service.py       -> valida plan, tenant, limites y aprovisionamiento
stripe_service.py              -> crea checkout y valida webhook de Stripe
notificaciones_service.py      -> crea notificaciones
notificaciones_realtime.py     -> maneja conexiones WebSocket
auth_service.py                -> token, password y bitacora
```

En defensa puedes decir:

```txt
Los services evitan repetir logica en varios routers.
```

### app/ia/

Contiene servicios de inteligencia artificial.

Ejemplos:

```txt
audio_service.py   -> transcribe audios
imagen_service.py  -> analiza imagenes
```

Caso de uso relacionado:

```txt
CU: Registrar evidencia multimedia y transcribir audio
```

### migrations/

Contiene los scripts SQL para actualizar la base de datos.

Ejemplos importantes:

```txt
009_add_offline_sync_incidentes.sql
010_create_conflictos_sincronizacion.sql
012_add_stripe_subscriptions.sql
013_create_pagos_comprobantes_suscripcion.sql
016_backfill_tenants_free_subscription.sql
```

En defensa puedes decir:

```txt
Las migraciones permiten que la base de datos tenga las nuevas tablas y columnas de los casos de uso implementados.
```

### uploads/

Carpeta donde el backend guarda archivos subidos.

Ejemplos:

```txt
imagenes de evidencia
audios de evidencia
```

## 3. Mapa de casos de uso

### CU: Registrar incidente online

Ubicacion:

```txt
app/routers/incidentes.py
app/schemas/incidente.py
app/models/operaciones.py
```

Endpoint:

```http
POST /incidentes
```

Que hace:

```txt
Recibe los datos del incidente desde el frontend.
Valida el JSON con IncidenteCreate.
Guarda el incidente en la tabla incidente.
```

Flujo:

```txt
Frontend movil/web
-> POST /incidentes
-> router incidentes.py
-> schema IncidenteCreate
-> model Incidente
-> PostgreSQL
```

### CU: Registrar incidente offline local

Ubicacion movil:

```txt
Flutter
SQLite local del dispositivo
```

Ubicacion backend:

```txt
app/routers/sync.py
app/schemas/sync.py
app/schemas/incidente.py
app/models/operaciones.py
```

Endpoint de sincronizacion:

```http
POST /sync/incidentes
```

Que hace:

```txt
Cuando no hay internet, la app guarda el incidente en SQLite.
Cuando vuelve internet, la app envia el incidente al backend.
El backend registra el incidente en PostgreSQL y conserva el id_local_origen.
```

Estados usados en movil:

```txt
PENDIENTE
SINCRONIZANDO
SINCRONIZADO
ERROR
SINCRONIZADO_PARCIAL
CONFLICTO
```

Campos importantes:

```txt
id_local_origen
origen_registro = OFFLINE
fecha_creacion_local
version_local
estado_local_origen
```

### CU: Resolver conflicto de sincronizacion offline

Ubicacion:

```txt
app/routers/sync.py
app/models/operaciones.py
```

Endpoints:

```http
GET /sync/conflictos
GET /sync/pendientes
POST /sync/resolver-conflicto/{id_conflicto}
```

Que hace:

```txt
Detecta posibles incidentes duplicados.
Guarda el conflicto en la tabla conflicto_sincronizacion.
Permite resolverlo manualmente.
```

Acciones:

```txt
CONSERVAR_SERVIDOR
CREAR_NUEVO
FUSIONAR_EVIDENCIAS
DESCARTAR_LOCAL
```

### CU: Subir evidencias del incidente

Ubicacion:

```txt
app/routers/evidencias.py
app/models/multimedia.py
app/ia/audio_service.py
app/ia/imagen_service.py
```

Endpoints:

```http
POST /evidencias/imagen/{id_incidente}
POST /evidencias/audio/{id_incidente}
POST /evidencias/texto/{id_incidente}
POST /evidencias/multiple/{id_incidente}
GET /evidencias/{id_incidente}
```

Que hace:

```txt
Guarda fotos, audios y texto del incidente.
Los archivos se almacenan en uploads.
El registro queda en la tabla evidencia.
Si es audio, se manda a transcripcion.
Si es imagen, se manda a analisis de imagen.
```

### CU: Transcribir audio de evidencia

Ubicacion:

```txt
app/routers/evidencias.py
app/ia/audio_service.py
app/models/multimedia.py
```

Endpoint:

```http
POST /evidencias/audio/{id_incidente}
```

Que hace:

```txt
Recibe uno o varios audios.
Guarda el archivo.
Llama a transcribir_audio.
Guarda la transcripcion en la columna transcripcion de evidencia.
```

### CU: Analizar imagen de evidencia

Ubicacion:

```txt
app/routers/evidencias.py
app/ia/imagen_service.py
app/models/multimedia.py
```

Endpoint:

```http
POST /evidencias/imagen/{id_incidente}
```

Que hace:

```txt
Recibe imagenes del incidente.
Guarda los archivos.
Ejecuta analisis de imagen.
Guarda la descripcion o resultado en evidencia.
```

### CU: Cotizar servicio

Ubicacion:

```txt
app/routers/cotizaciones.py
app/schemas/cotizaciones.py
app/models/cotizaciones.py
```

Que hace:

```txt
Permite que un cliente solicite cotizacion.
Permite que un taller responda la cotizacion.
Maneja estados del flujo de cotizacion.
```

Flujo general:

```txt
Cliente solicita cotizacion
-> Taller recibe solicitud
-> Taller responde precio/detalle
-> Cliente acepta o rechaza
```

### CU: Asignar tecnico al incidente

Ubicacion:

```txt
app/routers/asignacion.py
app/models/operaciones.py
app/models/talleres.py
```

Que hace:

```txt
Relaciona un incidente con un tecnico.
Registra fecha de asignacion.
Actualiza estados de asignacion.
```

### CU: Tracking del tecnico

Ubicacion:

```txt
app/routers/tracking.py
app/models/talleres.py
app/models/operaciones.py
app/services/notificaciones_service.py
```

Que hace:

```txt
Actualiza la ubicacion del tecnico.
Permite consultar si el tecnico esta en camino o cerca.
Dispara notificaciones cuando corresponde.
```

Ejemplo para defensa:

```txt
Cuando el tecnico esta cerca, el backend crea una notificacion para el cliente.
```

### CU: Validar arribo del tecnico

Ubicacion:

```txt
app/routers/validacion_arribo.py
```

Que hace:

```txt
Permite confirmar que el tecnico llego al punto del incidente.
Ayuda a controlar el avance real del servicio.
```

### CU: Notificaciones en tiempo real

Ubicacion:

```txt
app/routers/notificaciones.py
app/services/notificaciones_service.py
app/services/notificaciones_realtime.py
app/models/notificaciones.py
```

Endpoints:

```http
GET /notificaciones
POST /notificaciones
POST /notificaciones/broadcast
WebSocket /notificaciones/ws?token=...
```

Que hace:

```txt
Crea notificaciones en la base de datos.
Marca notificaciones como leidas.
Envia eventos en tiempo real por WebSocket.
```

Casos:

```txt
Tecnico en camino
Tecnico cerca
Nueva cotizacion
Novedades del taller
Avisos generales
```

### CU: Gestionar talleres

Ubicacion:

```txt
app/routers/talleres.py
app/models/talleres.py
app/schemas/taller.py
app/services/suscripciones_service.py
```

Que hace:

```txt
Crea, lista y administra talleres.
Cuando se crea un taller nuevo, tambien se crea su tenant y su suscripcion gratis.
```

Punto importante:

```txt
El backend llama a aprovisionar_tenant_gratis_taller.
```

### CU: Solicitud de registro de taller

Ubicacion:

```txt
app/routers/solicitudes.py
app/services/suscripciones_service.py
```

Que hace:

```txt
Un taller puede solicitar registro.
El administrador acepta o rechaza la solicitud.
Si se acepta, se activa el taller y se crea su tenant gratis.
```

### CU: Gestionar tecnicos

Ubicacion:

```txt
app/routers/tecnicos.py
app/models/talleres.py
app/schemas/tecnico.py
app/services/suscripciones_service.py
```

Que hace:

```txt
Permite registrar tecnicos de un taller.
Valida limites segun la suscripcion del taller.
```

### CU: Gestionar vehiculos

Ubicacion:

```txt
app/routers/vehiculos.py
app/models/talleres.py
app/schemas/vehiculo.py
```

Que hace:

```txt
Permite registrar y consultar vehiculos del cliente.
El incidente se asocia a un vehiculo.
```

### CU: Gestionar usuarios, roles y permisos

Ubicacion:

```txt
app/routers/auth.py
app/routers/usuarios.py
app/models/seguridad.py
app/services/auth_service.py
```

Endpoints importantes:

```http
POST /auth/login
POST /auth/register
```

Que hace:

```txt
Registra usuarios.
Valida credenciales.
Genera token JWT.
Controla roles y permisos.
```

### CU: Suscripcion de talleres y tenant

Ubicacion:

```txt
app/routers/suscripciones.py
app/services/suscripciones_service.py
app/models/suscripciones.py
app/schemas/suscripciones.py
```

Endpoints importantes:

```http
GET /suscripciones/mi-plan
GET /suscripciones/plan-estandar
POST /suscripciones/backfill/tenants-gratis
GET /suscripciones/planes
POST /suscripciones/tenants
PUT /suscripciones/tenants/{id_tenant}/plan
```

Que hace:

```txt
Administra tenants.
Administra planes.
Consulta el plan actual del taller.
Crea suscripciones.
Valida si el taller puede operar.
```

Punto importante para defensa:

```txt
Los talleres antiguos se regularizan con /suscripciones/backfill/tenants-gratis.
Los talleres nuevos nacen automaticamente con tenant y plan gratuito de 0 Bs.
```

### CU: Pago de suscripcion con Stripe

Ubicacion:

```txt
app/routers/suscripciones.py
app/services/stripe_service.py
app/models/suscripciones.py
app/config.py
```

Endpoints:

```http
POST /suscripciones/tenants/{id_tenant}/checkout
POST /suscripciones/stripe/webhook
GET /suscripciones/tenants/{id_tenant}/pagos
GET /suscripciones/tenants/{id_tenant}/comprobantes
```

Que hace:

```txt
Crea una sesion de pago con Stripe.
Recibe eventos de Stripe por webhook.
Registra pagos de suscripcion.
Genera comprobantes.
```

Variables necesarias:

```txt
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_SUCCESS_URL
STRIPE_CANCEL_URL
```

Webhook correcto:

```txt
/suscripciones/stripe/webhook
```

### CU: Registrar pago del servicio vehicular

Ubicacion:

```txt
app/routers/pagos.py
app/models/operaciones.py
```

Que hace:

```txt
Registra el pago del servicio asociado al incidente.
No es lo mismo que el pago de suscripcion del taller.
```

### CU: Evaluar servicio

Ubicacion:

```txt
app/routers/evaluaciones.py
```

Que hace:

```txt
Permite que el cliente califique la atencion recibida.
```

### CU: Chat del incidente

Ubicacion:

```txt
app/routers/chat.py
app/models/operaciones.py
```

Que hace:

```txt
Permite comunicacion relacionada con el incidente.
Guarda mensajes del flujo de atencion.
```

### CU: Dashboard administrativo

Ubicacion:

```txt
app/routers/dashboard.py
```

Que hace:

```txt
Entrega metricas y resumenes para administradores.
```

## 4. Flujo completo del sistema

```txt
1. Cliente inicia sesion.
2. Cliente registra vehiculo.
3. Cliente reporta incidente.
4. Si hay internet, se guarda directo en PostgreSQL.
5. Si no hay internet, se guarda en SQLite del movil.
6. Cuando vuelve internet, Flutter llama POST /sync/incidentes.
7. Backend guarda el incidente offline en PostgreSQL.
8. Flutter sube evidencias.
9. Backend transcribe audio y analiza imagenes.
10. Taller recibe solicitud o cotizacion.
11. Taller responde cotizacion.
12. Se asigna tecnico.
13. Tecnico actualiza ubicacion.
14. Cliente recibe notificaciones en tiempo real.
15. Tecnico llega y atiende.
16. Se registra pago del servicio.
17. Cliente evalua el servicio.
```

## 5. Flujo de suscripcion de taller

```txt
1. Se crea un taller.
2. Backend crea automaticamente tenant.
3. Backend crea dominio tipo subdominio.
4. Backend crea suscripcion activa.
5. Si es plan estandar, el costo es 0 Bs.
6. Si despues se configura plan pagado, se usa Stripe Checkout.
7. Stripe confirma pago por webhook.
8. Backend registra pago y comprobante.
```

## 6. Diferencia entre SQLite y PostgreSQL

### SQLite

Se usa en el movil.

Responsabilidad:

```txt
Guardar incidentes offline cuando no hay internet.
Guardar evidencias pendientes.
Guardar estado de sincronizacion.
```

### PostgreSQL

Se usa en el backend.

Responsabilidad:

```txt
Guardar datos oficiales del sistema.
Guardar incidentes sincronizados.
Guardar evidencias recibidas.
Guardar usuarios, talleres, tecnicos, tenants, suscripciones y pagos.
```

Frase para defensa:

```txt
SQLite es una cola local temporal para no perder informacion sin internet.
PostgreSQL es la base de datos oficial del sistema una vez que se sincroniza.
```

## 7. Endpoints clave para la defensa

```txt
POST /auth/login
POST /incidentes
POST /sync/incidentes
GET /sync/conflictos
POST /sync/resolver-conflicto/{id_conflicto}
POST /evidencias/imagen/{id_incidente}
POST /evidencias/audio/{id_incidente}
POST /evidencias/texto/{id_incidente}
GET /suscripciones/mi-plan
POST /suscripciones/backfill/tenants-gratis
POST /suscripciones/tenants/{id_tenant}/checkout
POST /suscripciones/stripe/webhook
WebSocket /notificaciones/ws?token=...
```

## 8. Como explicar el backend en una frase

```txt
El backend esta organizado por modulos. Cada router expone endpoints de un caso de uso, los schemas validan el JSON, los models representan las tablas, los services contienen reglas de negocio y las migraciones actualizan la base de datos.
```

## 9. Como explicar el modo offline en una frase

```txt
Cuando no hay internet, Flutter guarda el incidente en SQLite con un id_local_origen. Cuando vuelve la conexion, envia ese registro a /sync/incidentes y el backend lo guarda en PostgreSQL manteniendo la relacion entre el id local y el id real del servidor.
```

## 10. Como explicar Stripe en una frase

```txt
Stripe se usa solo para planes pagados. El backend crea la sesion de checkout, Stripe procesa el pago y luego confirma el resultado mediante el webhook /suscripciones/stripe/webhook.
```


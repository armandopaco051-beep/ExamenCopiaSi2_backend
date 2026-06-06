INSERT INTO catalogo.estado_asignacion (id, nombre)
VALUES
    (9, 'Servicio aceptado por tecnico'),
    (10, 'Tecnico llego'),
    (11, 'Atencion iniciada')
ON CONFLICT (id) DO UPDATE
SET nombre = EXCLUDED.nombre;

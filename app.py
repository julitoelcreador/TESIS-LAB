from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_from_directory
)
from markupsafe import escape
from contextlib import contextmanager
import difflib
import re
import uuid
import uuid
import sqlite3
import os
from pathlib import Path
from functools import wraps
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid
from werkzeug.utils import secure_filename


def get_db():
    conn = sqlite3.connect("database/investigacion.db")
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# AULA INVESTIGA
# Recurso Educativo Digital para la gestión, orientación,
# colaboración y evaluación de trabajos de investigación
# académica - La Salle
# ============================================================


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "database"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

DB_PATH = DATA_DIR / "investigacion.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "AulaInvestiga_LaSalle_2026_Cambiar"
)

app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)


ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "odt",
    "txt",
    "png",
    "jpg",
    "jpeg"
}

# ============================================================
# LOGIN REQUERIDO
# ============================================================
def login_requerido(func):

    @wraps(func)
    def decorador(*args, **kwargs):

        if not session.get("usuario_id"):

            flash(
                "Inicia sesión para continuar.",
                "aviso"
            )

            return redirect(
                url_for("login")
            )

        if not usuario_actual():

            session.clear()

            flash(
                "Tu sesión ya no es válida.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return func(*args, **kwargs)

    return decorador


# ============================================================
# SOLO ADMINISTRADORES
# ============================================================

def administrador_requerido(func):

    @wraps(func)
    @login_requerido
    def decorador(*args, **kwargs):

        usuario = usuario_actual()

        if usuario["rol"] != "admin":
            flash(
                "No tienes permiso para administrar el cronograma.",
                "error"
            )
            return redirect(url_for("cronograma"))

        return func(*args, **kwargs)

    return decorador


# ============================================================
# CONEXIÓN A BASE DE DATOS
# ============================================================

@contextmanager
def conectar_db():

    conexion = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conexion.row_factory = sqlite3.Row

    conexion.execute(
        "PRAGMA foreign_keys = ON"
    )

    conexion.execute(
        "PRAGMA busy_timeout = 30000"
    )

    try:

        yield conexion

        conexion.commit()

    except Exception:

        conexion.rollback()
        raise

    finally:

        conexion.close()




# ============================================================
# NOTIFICACIONES — CREACIÓN SEGURA
# ============================================================

def asegurar_tabla_notificaciones(db):
    """Crea la tabla de notificaciones si todavía no existe."""

    db.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            investigacion_id INTEGER,
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            enlace TEXT,
            leida INTEGER NOT NULL DEFAULT 0,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario
        ON notificaciones (usuario_id, leida, creado_en)
    """)


def crear_notificacion(
    db,
    usuario_id,
    titulo,
    mensaje,
    investigacion_id=None,
    enlace=None
):
    """Guarda una notificación y confirma si se insertó."""

    if not usuario_id:
        return False

    asegurar_tabla_notificaciones(db)

    cursor = db.execute(
        """
        INSERT INTO notificaciones (
            usuario_id,
            investigacion_id,
            titulo,
            mensaje,
            enlace,
            leida
        )
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            usuario_id,
            investigacion_id,
            titulo,
            mensaje,
            enlace
        )
    )

    return cursor.rowcount == 1


# ============================================================
# OBTENER USUARIO ACTUAL
# ============================================================

def usuario_actual():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return None

    try:
        with conectar_db() as db:
            usuario = db.execute(
                """
                SELECT *
                FROM usuarios
                WHERE id = ?
                  AND activo = 1
                """,
                (usuario_id,)
            ).fetchone()

            if usuario is None:
                return None

            return usuario

    except sqlite3.Error:
        return None



# ============================================================
# VERIFICAR SI UN ESTUDIANTE PERTENECE A UNA INVESTIGACIÓN
# ============================================================

def es_miembro_investigacion(usuario_id, investigacion_id):

    with conectar_db() as db:

        miembro = db.execute(
            """
            SELECT mg.id
            FROM miembros_grupo AS mg
            INNER JOIN investigaciones AS i
                ON i.grupo_id = mg.grupo_id
            WHERE mg.estudiante_id = ?
              AND i.id = ?
              AND mg.estado = 'activo'
            LIMIT 1
            """,
            (usuario_id, investigacion_id)
        ).fetchone()

    return miembro is not None


# ============================================================
# HISTORIAL DE PROGRESO - AULAINVESTIGA
# ============================================================

def preparar_historial_progreso():
    """Crea la tabla histórica sin borrar datos existentes."""

    with conectar_db() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_progreso (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investigacion_id INTEGER,
                nivel INTEGER NOT NULL,
                evento TEXT NOT NULL,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (investigacion_id)
                    REFERENCES investigaciones(id)
            )
            """
        )


def registrar_evento_progreso_db(
    db,
    investigacion_id,
    nivel,
    evento
):
    """Registra un evento usando la conexión actual."""

    preparar_tabla = """
        CREATE TABLE IF NOT EXISTS historial_progreso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER,
            nivel INTEGER NOT NULL,
            evento TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id)
        )
    """

    db.execute(preparar_tabla)

    db.execute(
        """
        INSERT INTO historial_progreso (
            investigacion_id,
            nivel,
            evento
        )
        VALUES (?, ?, ?)
        """,
        (
            investigacion_id,
            nivel,
            evento
        )
    )


def registrar_evento_progreso(
    investigacion_id,
    nivel,
    evento
):
    """Guarda un evento real del flujo de investigación."""

    preparar_historial_progreso()

    with conectar_db() as db:

        db.execute(
            """
            INSERT INTO historial_progreso (
                investigacion_id,
                nivel,
                evento
            )
            VALUES (?, ?, ?)
            """,
            (
                investigacion_id,
                nivel,
                evento
            )
        )


def registrar_evento_progreso(investigacion_id, nivel, evento):
    """Guarda un evento real del flujo de investigación."""
    preparar_historial_progreso()

    with conectar_db() as db:
        db.execute("""
            INSERT INTO historial_progreso
                (investigacion_id, nivel, evento)
            VALUES (?, ?, ?)
        """, (investigacion_id, nivel, evento))



def registrar_evento_progreso_db(
    db,
    investigacion_id,
    nivel,
    evento
):
    """Registra un evento usando la conexión actual."""

    db.execute("""
        CREATE TABLE IF NOT EXISTS historial_progreso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER,
            nivel INTEGER NOT NULL,
            evento TEXT NOT NULL,
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id)
        )
    """)

    db.execute("""
        INSERT INTO historial_progreso (
            investigacion_id,
            nivel,
            evento
        )
        VALUES (?, ?, ?)
    """, (
        investigacion_id,
        nivel,
        evento
    ))

def registrar_evento_progreso(investigacion_id, nivel, evento):
    """Guarda un evento real del flujo de investigación."""
    preparar_historial_progreso()

    with conectar_db() as db:
        db.execute("""
            INSERT INTO historial_progreso
                (investigacion_id, nivel, evento)
            VALUES (?, ?, ?)
        """, (investigacion_id, nivel, evento))





# ============================================================
# HISTORIAL DE PROGRESO - ADMINISTRADOR
# ============================================================

@app.route("/admin/historial-progreso")
@login_requerido
def admin_historial_progreso():

    usuario = usuario_actual()

    # --------------------------------------------------------
    # VERIFICAR PERMISOS
    # --------------------------------------------------------

    if usuario["rol"] != "admin":
        flash(
            "No tienes permiso para ver el historial de progreso.",
            "error"
        )
        return redirect(url_for("panel"))

    preparar_historial_progreso()

    # --------------------------------------------------------
    # CONSULTAR INVESTIGACIONES Y SU PROGRESO
    # --------------------------------------------------------

    with conectar_db() as db:

        investigaciones = db.execute("""
            SELECT
                i.id,
                i.titulo,
                i.nivel_actual,
                g.nombre AS grupo_nombre,

                COUNT(
                    CASE
                        WHEN LOWER(TRIM(ni.estado)) = 'aprobado'
                        THEN 1
                    END
                ) AS niveles_aprobados,

                ROUND(
                    COUNT(
                        CASE
                            WHEN LOWER(TRIM(ni.estado)) = 'aprobado'
                            THEN 1
                        END
                    ) * 100.0 / 6
                ) AS porcentaje_avance

            FROM investigaciones i

            INNER JOIN grupos g
                ON g.id = i.grupo_id

            LEFT JOIN niveles_investigacion ni
                ON ni.investigacion_id = i.id

            GROUP BY
                i.id,
                i.titulo,
                i.nivel_actual,
                g.nombre

            ORDER BY i.creado_en DESC

        """).fetchall()

        # ----------------------------------------------------
        # CONSULTAR HISTORIAL DE EVENTOS
        # ----------------------------------------------------

        historial = db.execute("""
            SELECT
                date(fecha) AS fecha,
                evento,
                COUNT(*) AS cantidad

            FROM historial_progreso

            GROUP BY
                date(fecha),
                evento

            ORDER BY date(fecha) ASC

        """).fetchall()

    # --------------------------------------------------------
    # CALCULAR AVANCE PROMEDIO
    # --------------------------------------------------------

    if investigaciones:

        avance_promedio = round(
            sum(
                fila["porcentaje_avance"]
                for fila in investigaciones
            ) / len(investigaciones)
        )

    else:
        avance_promedio = 0

    # --------------------------------------------------------
    # CONTAR INVESTIGACIONES POR NIVEL ACTUAL
    # --------------------------------------------------------

    investigaciones_por_nivel = []

    for nivel in range(1, 7):

        cantidad = sum(
            1
            for fila in investigaciones
            if fila["nivel_actual"] == nivel
        )

        investigaciones_por_nivel.append({
            "nivel": nivel,
            "cantidad": cantidad
        })

    # --------------------------------------------------------
    # MOSTRAR PÁGINA
    # --------------------------------------------------------

    return render_template(
        "historial_progreso.html",
        usuario=usuario,
        investigaciones=investigaciones,
        historial=[dict(fila) for fila in historial],
        avance_promedio=avance_promedio,
        investigaciones_por_nivel=investigaciones_por_nivel,
        total_investigaciones=len(investigaciones)
    )


# ============================================================
# INICIALIZAR BASE DE DATOS
# ============================================================




def inicializar_db():
    with conectar_db() as db:

        # ========================================================
        # CREACION DE TABLAS
        # ========================================================

        db.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            correo TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL
                CHECK (rol IN ('admin', 'tutor', 'estudiante')),
            curso TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS especialidades_catalogo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            investigacion_id INTEGER,
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            enlace TEXT,
            leida INTEGER NOT NULL DEFAULT 0,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario
        ON notificaciones(usuario_id, leida, creado_en);

        CREATE TABLE IF NOT EXISTS especialidades_tutor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutor_id INTEGER NOT NULL,
            especialidad TEXT NOT NULL,
            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            UNIQUE (tutor_id, especialidad)
        );

        CREATE TABLE IF NOT EXISTS grupos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            lider_id INTEGER NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lider_id)
                REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS miembros_grupo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id INTEGER NOT NULL,
            estudiante_id INTEGER NOT NULL,
            es_lider INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'activo',
            FOREIGN KEY (grupo_id)
                REFERENCES grupos(id) ON DELETE CASCADE,
            FOREIGN KEY (estudiante_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            UNIQUE (grupo_id, estudiante_id)
        );

        CREATE TABLE IF NOT EXISTS invitaciones_grupo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id INTEGER NOT NULL,
            invitado_id INTEGER NOT NULL,
            invitado_por INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (grupo_id)
                REFERENCES grupos(id) ON DELETE CASCADE,
            FOREIGN KEY (invitado_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (invitado_por)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS investigaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            area_principal TEXT NOT NULL,
            subarea TEXT NOT NULL,
            profesor_id INTEGER,
            nivel_actual INTEGER NOT NULL DEFAULT 1,
            estado TEXT NOT NULL DEFAULT 'En proceso',
            estado_evaluacion TEXT NOT NULL DEFAULT 'Bloqueado',
            nota_final REAL,
            nota_visible INTEGER NOT NULL DEFAULT 0,
            finalizada INTEGER NOT NULL DEFAULT 0,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (grupo_id)
                REFERENCES grupos(id) ON DELETE CASCADE,
            FOREIGN KEY (profesor_id)
                REFERENCES usuarios(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS solicitudes_asignacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            propuesto_por INTEGER NOT NULL,
            tipo TEXT NOT NULL
                CHECK (tipo IN ('admin_a_tutor', 'tutor_a_admin')),
            estado TEXT NOT NULL DEFAULT 'Pendiente'
                CHECK (estado IN ('Pendiente', 'Aceptada', 'Rechazada')),
            respuesta_en TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (propuesto_por)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS niveles_investigacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Bloqueado',
            observaciones TEXT,
            nota REAL,
            evaluado INTEGER NOT NULL DEFAULT 0,
            enviado_en TEXT,
            revisado_en TEXT,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            UNIQUE (investigacion_id, nivel)
        );

        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            archivo TEXT,
            texto TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            comentario_profesor TEXT,
            enviado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            revisado_en TEXT,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            UNIQUE (investigacion_id, nivel)
        );

        CREATE TABLE IF NOT EXISTS historial_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entrega_id INTEGER NOT NULL,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            version INTEGER NOT NULL,
            archivo TEXT,
            texto TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'Pendiente de revisión',
            observaciones TEXT,
            nota REAL,
            enviado_por INTEGER,
            enviado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revisado_en TEXT,
            UNIQUE (investigacion_id, nivel, version),
            FOREIGN KEY (entrega_id)
                REFERENCES entregas(id) ON DELETE CASCADE,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (enviado_por)
                REFERENCES usuarios(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS observaciones_correccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            historial_entrega_id INTEGER NOT NULL,
            texto TEXT NOT NULL,
            corregida INTEGER NOT NULL DEFAULT 0,
            corregida_en TEXT,
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (historial_entrega_id)
                REFERENCES historial_entregas(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_observaciones_historial
        ON observaciones_correccion(historial_entrega_id);

        CREATE TABLE IF NOT EXISTS revisiones_correcciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            historial_anterior_id INTEGER NOT NULL,
            historial_nuevo_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            total_observaciones INTEGER NOT NULL DEFAULT 0,
            atendidas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0,
            registrado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (historial_anterior_id)
                REFERENCES historial_entregas(id) ON DELETE CASCADE,
            FOREIGN KEY (historial_nuevo_id)
                REFERENCES historial_entregas(id) ON DELETE CASCADE,
            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            UNIQUE (historial_anterior_id, historial_nuevo_id)
        );

        CREATE TABLE IF NOT EXISTS comentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            autor_id INTEGER NOT NULL,
            mensaje TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (autor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS fuentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            autor TEXT NOT NULL,
            anio TEXT,
            titulo TEXT NOT NULL,
            tipo TEXT,
            url TEXT,
            fecha_consulta TEXT,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tareas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            fecha_limite TEXT,
            completada INTEGER NOT NULL DEFAULT 0,
            creada_por INTEGER NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (creada_por)
                REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS eventos_cronograma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            fecha TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fin TEXT,
            tipo TEXT NOT NULL DEFAULT 'Hito',
            activa INTEGER NOT NULL DEFAULT 1,
            creada_por INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modificada_en TEXT,
            FOREIGN KEY (creada_por)
                REFERENCES usuarios(id) ON DELETE SET NULL,
            UNIQUE (titulo, fecha)
        );

        CREATE INDEX IF NOT EXISTS idx_eventos_cronograma_fecha
        ON eventos_cronograma(fecha, hora_inicio);

        CREATE TABLE IF NOT EXISTS recursos_biblioteca (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            tipo TEXT,
            nivel INTEGER,
            area_principal TEXT,
            subarea TEXT,
            url TEXT,
            archivo TEXT,
            gestion TEXT,
            creado_por INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creado_por)
                REFERENCES usuarios(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS permisos_biblioteca (
            tutor_id INTEGER PRIMARY KEY,
            puede_publicar INTEGER NOT NULL DEFAULT 0
                CHECK (puede_publicar IN (0, 1)),
            puede_editar INTEGER NOT NULL DEFAULT 0,
            puede_eliminar INTEGER NOT NULL DEFAULT 0,
            puede_gestionar INTEGER NOT NULL DEFAULT 0,
            modificado_por INTEGER,
            modificado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY (modificado_por)
                REFERENCES usuarios(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS mensajes_chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            autor_id INTEGER NOT NULL,
            mensaje TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (autor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS solicitudes_reunion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            estudiante_id INTEGER NOT NULL,
            motivo TEXT NOT NULL,
            fecha_solicitada TEXT NOT NULL,
            hora_solicitada TEXT NOT NULL,
            duracion INTEGER DEFAULT 30,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            respuesta_profesor TEXT,
            fecha_creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (estudiante_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS rubricas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            evaluador_id INTEGER NOT NULL,
            criterio1 INTEGER DEFAULT 0,
            criterio2 INTEGER DEFAULT 0,
            criterio3 INTEGER DEFAULT 0,
            criterio4 INTEGER DEFAULT 0,
            criterio5 INTEGER DEFAULT 0,
            observaciones TEXT,
            puntaje REAL DEFAULT 0,
            evaluado_en TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (evaluador_id)
                REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS rubricas_criterios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutor_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            puntaje_maximo REAL NOT NULL,
            orden INTEGER NOT NULL DEFAULT 1,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS rubricas_evaluaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            historial_entrega_id INTEGER NOT NULL UNIQUE,
            evaluador_id INTEGER NOT NULL,
            puntaje_total REAL NOT NULL DEFAULT 0,
            observaciones TEXT,
            evaluado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY (historial_entrega_id)
                REFERENCES historial_entregas(id) ON DELETE CASCADE,
            FOREIGN KEY (evaluador_id)
                REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS rubricas_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluacion_id INTEGER NOT NULL,
            criterio_nombre TEXT NOT NULL,
            puntaje_maximo REAL NOT NULL,
            puntaje_obtenido REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (evaluacion_id)
                REFERENCES rubricas_evaluaciones(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_rubricas_criterios_tutor
        ON rubricas_criterios(tutor_id, activo);

        CREATE INDEX IF NOT EXISTS idx_rubricas_evaluaciones_investigacion
        ON rubricas_evaluaciones(investigacion_id, nivel);
        """)

        # ========================================================
        # MIGRACION DEL COMPARADOR DE CORRECCIONES
        # ========================================================

        columnas_observaciones = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(observaciones_correccion)"
            ).fetchall()
        ]

        if "revisada_por" not in columnas_observaciones:
            db.execute("""
                ALTER TABLE observaciones_correccion
                ADD COLUMN revisada_por INTEGER
                REFERENCES usuarios(id) ON DELETE SET NULL
            """)

        if "revisada_en" not in columnas_observaciones:
            db.execute("""
                ALTER TABLE observaciones_correccion
                ADD COLUMN revisada_en TEXT
            """)

        # ========================================================
        # ACTUALIZAR TABLA DE LA BIBLIOTECA VIRTUAL
        # ========================================================

        columnas_biblioteca = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(recursos_biblioteca)"
            ).fetchall()
        ]

        nuevas_columnas_biblioteca = {
            "autor": "TEXT",
            "anio_publicacion": "TEXT",
            "palabras_clave": "TEXT",
            "cita_apa": "TEXT"
        }

        for nombre_columna, tipo_columna in nuevas_columnas_biblioteca.items():
            if nombre_columna not in columnas_biblioteca:
                db.execute(
                    f"""
                    ALTER TABLE recursos_biblioteca
                    ADD COLUMN {nombre_columna} {tipo_columna}
                    """
                )

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_biblioteca_titulo
            ON recursos_biblioteca(titulo)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_biblioteca_area_tipo
            ON recursos_biblioteca(area_principal, tipo)
        """)
        # --------------------------------------------------------
        # MIGRACIÓN: ESTADO DE REVISIÓN DE LAS CORRECCIONES
        # --------------------------------------------------------

        columnas_observaciones = {
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(observaciones_correccion)"
            ).fetchall()
        }

        if "estado_revision" not in columnas_observaciones:
            db.execute("""
                ALTER TABLE observaciones_correccion
                ADD COLUMN estado_revision TEXT NOT NULL DEFAULT 'Pendiente'
            """)

        print("OK: estado_revision de observaciones verificado.")

    if "estado_revision" not in columnas_observaciones:
        db.execute("""
        ALTER TABLE observaciones_correccion
        ADD COLUMN estado_revision TEXT NOT NULL DEFAULT 'Pendiente'
        """)
        # ========================================================
        # ACTUALIZAR TABLAS DE ENTREGAS
        # ========================================================

        columnas_entregas = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(entregas)"
            ).fetchall()
        ]

        if "titulo" not in columnas_entregas:
            db.execute("""
                ALTER TABLE entregas
                ADD COLUMN titulo TEXT
            """)

        if "nota_estudiante" not in columnas_entregas:
            db.execute("""
                ALTER TABLE entregas
                ADD COLUMN nota_estudiante TEXT
            """)

        columnas_historial = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(historial_entregas)"
            ).fetchall()
        ]

        if "titulo" not in columnas_historial:
            db.execute("""
                ALTER TABLE historial_entregas
                ADD COLUMN titulo TEXT
            """)

        if "nota_estudiante" not in columnas_historial:
            db.execute("""
                ALTER TABLE historial_entregas
                ADD COLUMN nota_estudiante TEXT
            """)

        # ========================================================
        # ACTUALIZAR TABLA DE SOLICITUDES DE REUNION
        # ========================================================

        columnas_reunion = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(solicitudes_reunion)"
            ).fetchall()
        ]

        if "enlace_meet" not in columnas_reunion:
            db.execute("""
                ALTER TABLE solicitudes_reunion
                ADD COLUMN enlace_meet TEXT
            """)
            print("OK: columna enlace_meet creada.")
        else:
            print("OK: columna enlace_meet ya existe.")

        # ========================================================
        # ESPECIALIDADES DEL CATALOGO
        # ========================================================

        especialidades = [
            "Social",
            "Psicológico",
            "Espiritual",
            "Judicial",
            "Medio ambiente",
            "Salud",
            "Nutrición",
            "Alimentación",
            "Ingeniería",
            "Contabilidad",
            "Científico",
            "Tecnológico"
        ]

        for especialidad in especialidades:
            db.execute(
                """
                INSERT OR IGNORE INTO especialidades_catalogo (nombre)
                VALUES (?)
                """,
                (especialidad,)
            )

        # ========================================================
        # ADMINISTRADOR INICIAL
        # ========================================================

        admin = db.execute(
            "SELECT id FROM usuarios WHERE usuario = ?",
            ("director",)
        ).fetchone()

        if not admin:
            db.execute(
                """
                INSERT INTO usuarios (
                    nombre, apellido, usuario, correo,
                    password_hash, rol
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Director",
                    "La Salle",
                    "director",
                    "admin@aulainvestiga.local",
                    generate_password_hash("Admin123!"),
                    "admin"
                )
            )

        # ========================================================
        # CRONOGRAMA OFICIAL DE LA GESTION 2026
        # ========================================================

        administrador = db.execute(
            "SELECT id FROM usuarios WHERE usuario = ?",
            ("director",)
        ).fetchone()

        administrador_id = administrador["id"]

        eventos_oficiales = [
            (
                "Socialización de la convocatoria",
                "Presentación de las indicaciones generales y del proceso de investigación.",
                "2026-08-10", None, None, "Hito"
            ),
            (
                "Presentación del tema elegido",
                "Fecha límite para presentar el tema de investigación.",
                "2026-08-18", "12:00", None, "Entrega"
            ),
            (
                "Primera presentación — Capítulo I",
                "Fecha límite para la presentación del primer capítulo.",
                "2026-09-01", "12:00", None, "Entrega"
            ),
            (
                "Segunda presentación — Capítulo II",
                "Fecha límite para la presentación del segundo capítulo.",
                "2026-09-22", "12:00", None, "Entrega"
            ),
            (
                "Tercera presentación — Capítulo III",
                "Fecha límite para la presentación del tercer capítulo.",
                "2026-10-13", "12:00", None, "Entrega"
            ),
            (
                "Cuarta presentación — Capítulo IV",
                "Fecha límite para la presentación del cuarto capítulo.",
                "2026-10-27", "12:00", None, "Entrega"
            ),
            (
                "Quinta presentación — Capítulo V",
                "Fecha límite para la presentación del quinto capítulo.",
                "2026-11-10", "12:00", None, "Entrega"
            ),
            (
                "Trabajo final — Coordinación",
                "Presentación del trabajo final para su coordinación.",
                "2026-11-16", "12:00", None, "Entrega"
            ),
            (
                "Exposición y defensa",
                "Jornada de exposición y defensa de las monografías.",
                "2026-11-21", "07:30", "11:00", "Defensa"
            )
        ]

        for evento in eventos_oficiales:
            db.execute(
                """
                INSERT OR IGNORE INTO eventos_cronograma (
                    titulo, descripcion, fecha, hora_inicio,
                    hora_fin, tipo, creada_por
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (*evento, administrador_id)
            )

        # ========================================================
        # PROFESOR DE PRUEBA
        # ========================================================

        profesor = db.execute(
            "SELECT id FROM usuarios WHERE usuario = ?",
            ("profesor1",)
        ).fetchone()

        if not profesor:
            cursor = db.execute(
                """
                INSERT INTO usuarios (
                    nombre, apellido, usuario, correo,
                    password_hash, rol
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Profesor",
                    "Ejemplo",
                    "profesor1",
                    "profesor1@aulainvestiga.local",
                    generate_password_hash("Prof123!"),
                    "tutor"
                )
            )
            profesor_id = cursor.lastrowid
        else:
            profesor_id = profesor["id"]

        db.execute(
            """
            INSERT OR IGNORE INTO especialidades_tutor (
                tutor_id, especialidad
            )
            VALUES (?, ?)
            """,
            (profesor_id, "Científico")
        )

        # ========================================================
        # ESTUDIANTE DE PRUEBA
        # ========================================================

        estudiante = db.execute(
            "SELECT id FROM usuarios WHERE usuario = ?",
            ("alumno1",)
        ).fetchone()

        if not estudiante:
            db.execute(
                """
                INSERT INTO usuarios (
                    nombre, apellido, usuario, correo,
                    password_hash, rol, curso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Alumno",
                    "Ejemplo",
                    "alumno1",
                    "alumno1@aulainvestiga.local",
                    generate_password_hash("Alumno123!"),
                    "estudiante",
                    "5º Secundaria"
                )
            )



def asegurar_tabla_recursos_biblioteca():
    """Prepara la tabla de Biblioteca sin perder recursos existentes."""

    with conectar_db() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS recursos_biblioteca (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                tipo TEXT,
                nivel INTEGER,
                area_principal TEXT,
                subarea TEXT,
                url TEXT,
                archivo TEXT,
                gestion TEXT,
                creado_por INTEGER,
                creado_en TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(recursos_biblioteca)"
            ).fetchall()
        }

        migraciones = {
            "descripcion": "TEXT",
            "tipo": "TEXT",
            "nivel": "INTEGER",
            "area_principal": "TEXT",
            "subarea": "TEXT",
            "url": "TEXT",
            "archivo": "TEXT",
            "gestion": "TEXT",
            "creado_por": "INTEGER",
            "creado_en": "TEXT",
            "autor": "TEXT",
            "anio_publicacion": "TEXT",
            "palabras_clave": "TEXT",
            "cita_apa": "TEXT"
        }

        for columna, definicion in migraciones.items():

            if columna not in columnas:
                db.execute(
                    f"""
                    ALTER TABLE recursos_biblioteca
                    ADD COLUMN {columna} {definicion}
                    """
                )

        db.execute("""
            UPDATE recursos_biblioteca
            SET creado_en = CURRENT_TIMESTAMP
            WHERE creado_en IS NULL OR creado_en = ''
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_biblioteca_titulo
            ON recursos_biblioteca(titulo)
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_biblioteca_area_tipo
            ON recursos_biblioteca(area_principal, tipo)
        """)




def permisos_actuales_biblioteca(usuario):
    """Devuelve los permisos efectivos del usuario."""

    permisos_denegados = {
        "puede_publicar": 0,
        "puede_editar": 0,
        "puede_eliminar": 0,
        "puede_gestionar": 0,
        "puede_publicar_guias": 0,
        "puede_publicar_videos": 0,
        "puede_publicar_ejemplos": 0
    }

    # El administrador tiene acceso completo.
    if usuario["rol"] == "admin":
        return {
            clave: 1 for clave in permisos_denegados
        }

    # Los estudiantes no tienen permisos de publicación.
    if usuario["rol"] != "tutor":
        return permisos_denegados

    asegurar_columnas_permisos_biblioteca()

    with conectar_db() as db:

        fila = db.execute("""
            SELECT
                puede_publicar,
                puede_editar,
                puede_eliminar,
                puede_gestionar,
                puede_publicar_guias,
                puede_publicar_videos,
                puede_publicar_ejemplos
            FROM permisos_biblioteca
            WHERE tutor_id = ?
        """, (usuario["id"],)).fetchone()

    if not fila:
        return permisos_denegados

    return {
        "puede_publicar": int(fila["puede_publicar"] or 0),
        "puede_editar": int(fila["puede_editar"] or 0),
        "puede_eliminar": int(fila["puede_eliminar"] or 0),
        "puede_gestionar": int(fila["puede_gestionar"] or 0),
        "puede_publicar_guias": int(fila["puede_publicar_guias"] or 0),
        "puede_publicar_videos": int(fila["puede_publicar_videos"] or 0),
        "puede_publicar_ejemplos": int(fila["puede_publicar_ejemplos"] or 0)
    }




def permiso_biblioteca_requerido(usuario, permiso):
    """Comprueba si el usuario tiene autorización para una acción."""

    permisos = permisos_actuales_biblioteca(usuario)

    if usuario["rol"] == "admin":
        return True

    if usuario["rol"] != "tutor":
        return False

    return bool(
        permisos.get("puede_gestionar", 0)
        or permisos.get(permiso, 0)
    )


# ============================================================
# ROLES REQUERIDOS
# ============================================================

def roles_requeridos(*roles):

    def decorador(func):

        @wraps(func)
        def wrapper(*args, **kwargs):

            if not session.get("usuario_id"):

                return redirect(
                    url_for("login")
                )

            usuario = usuario_actual()

            if not usuario:

                session.clear()

                return redirect(
                    url_for("login")
                )

            if usuario["rol"] not in roles:

                flash(
                    "No tienes permiso para acceder a esta sección.",
                    "error"
                )

                return redirect(
                    url_for("panel")
                )

            return func(*args, **kwargs)

        return wrapper

    return decorador


# ============================================================
# ARCHIVOS PERMITIDOS
# ============================================================

def archivo_permitido(nombre):

    return (
        "."
        in nombre
        and
        nombre.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )

def ocultar_notas_estudiante(
    niveles
):

    resultado = []

    for nivel in niveles:

        datos = dict(nivel)

        datos["nota"] = None

        resultado.append(datos)

    return resultado


# ============================================================
# CONTEXTO GLOBAL PARA TODOS LOS TEMPLATES
# ============================================================

@app.context_processor
def contexto_global():
    usuario = None

    try:
        if session.get("usuario_id"):
            usuario = usuario_actual()
    except Exception:
        usuario = None

    return {
        "usuario_sesion": usuario,
        "anio_actual": datetime.now().year,
        "niveles": NIVELES,
        "areas": AREAS
    }
# ============================================================
# CONFIGURACIÓN DE NIVELES
# ============================================================

NIVELES = [
    {
        "nivel": 1,
        "titulo": "Presentación del tema elegido",
        "fecha": "18 de agosto a las 12:00",
        "capitulo": "Tema de investigación"
    },
    {
        "nivel": 2,
        "titulo": "Primera presentación",
        "fecha": "1 de septiembre a las 12:00",
        "capitulo": "Capítulo I"
    },
    {
        "nivel": 3,
        "titulo": "Segunda presentación",
        "fecha": "22 de septiembre a las 12:00",
        "capitulo": "Capítulo II"
    },
    {
        "nivel": 4,
        "titulo": "Tercera presentación",
        "fecha": "13 de octubre a las 12:00",
        "capitulo": "Capítulo III"
    },
    {
        "nivel": 5,
        "titulo": "Cuarta presentación",
        "fecha": "27 de octubre a las 12:00",
        "capitulo": "Capítulo IV"
    },
    {
        "nivel": 6,
        "titulo": "Quinta presentación",
        "fecha": "10 de noviembre a las 12:00",
        "capitulo": "Capítulo V"
    }
]


# ============================================================
# ÁREAS DE INVESTIGACIÓN
# ============================================================

AREAS = {

    "Campo social, psicológico, espiritual, judicial": [
        "Social",
        "Psicológico",
        "Espiritual",
        "Judicial"
    ],

    "Medio ambiente, salud, nutrición, alimentación": [
        "Medio ambiente",
        "Salud",
        "Nutrición",
        "Alimentación"
    ],

    "Adelantos de ingeniería, contabilidad, científicos y tecnológicos": [
        "Ingeniería",
        "Contabilidad",
        "Científico",
        "Tecnológico"
    ]

}


# ============================================================
# INICIO
# ============================================================

@app.route("/")
def inicio():

    if session.get("usuario_id"):

        return redirect(
            url_for("panel")
        )

    return render_template(
        "innovaciones/inicio.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        usuario_ingresado = request.form.get(
            "usuario",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )


        with conectar_db() as db:

            usuario = db.execute(
                """
                SELECT *
                FROM usuarios
                WHERE usuario = ?
                AND activo = 1
                """,
                (usuario_ingresado,)
            ).fetchone()


        if (
            usuario
            and
            check_password_hash(
                usuario["password_hash"],
                password
            )
        ):

            session.clear()

            session["usuario_id"] = usuario["id"]
            session["rol"] = usuario["rol"]
            session["nombre"] = usuario["nombre"]

            return redirect(
                url_for("panel")
            )


        flash(
            "Usuario o contraseña incorrectos.",
            "error"
        )


    return render_template(
        "innovaciones/login.html"
    )


# ============================================================
# CERRAR SESIÓN
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("inicio")
    )


@app.route("/admin/usuarios", methods=["GET", "POST"])
@login_requerido
def gestionar_usuarios():

    usuario = usuario_actual()

    if usuario["rol"] != "admin":
        flash("No tienes permiso para gestionar usuarios.", "error")
        return redirect(url_for("panel"))

    with conectar_db() as db:

        if request.method == "POST":

            nombre = request.form.get("nombre", "").strip()
            apellido = request.form.get("apellido", "").strip()
            nombre_usuario = request.form.get("usuario", "").strip()
            correo = request.form.get("correo", "").strip() or None
            password = request.form.get("password", "")
            rol = request.form.get("rol", "").strip()
            curso = request.form.get("curso", "").strip() or None
            especialidad = request.form.get("especialidad", "").strip()

            if not nombre or not apellido or not nombre_usuario or not password:
                flash("Completa los campos obligatorios.", "error")

            elif rol not in ("estudiante", "tutor"):
                flash("El rol seleccionado no es válido.", "error")

            elif len(password) < 8:
                flash("La contraseña debe tener al menos 8 caracteres.", "error")

            
            else:
                try:
                    existente = db.execute(
                        """
                        SELECT id FROM usuarios
                        WHERE usuario = ?
                           OR (? IS NOT NULL AND correo = ?)
                        """,
                        (nombre_usuario, correo, correo)
                    ).fetchone()

                    if existente:
                        flash("El usuario o correo ya está registrado.", "error")

                    else:
                        cursor = db.execute(
                            """
                            INSERT INTO usuarios (
                                nombre, apellido, usuario, correo,
                                password_hash, rol, curso
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                nombre,
                                apellido,
                                nombre_usuario,
                                correo,
                                generate_password_hash(password),
                                rol,
                                curso if rol == "estudiante" else None
                            )
                        )

                        
                        flash("Usuario creado correctamente.", "success")
                        return redirect(url_for("gestionar_usuarios"))

                except Exception:
                    flash(
                        "No se pudo crear el usuario. "
                        "Comprueba los datos e inténtalo de nuevo.",
                        "error"
                    )

        usuarios = db.execute(
            """
            SELECT id, nombre, apellido, usuario, correo,
                   rol, curso, activo, creado_en
            FROM usuarios
            ORDER BY creado_en DESC, id DESC
            """
        ).fetchall()

        especialidades = db.execute(
            """
            SELECT nombre
            FROM especialidades_catalogo
            ORDER BY nombre
            """
        ).fetchall()

    return render_template(
        "gestionar_usuarios.html",
        usuarios=usuarios,
        especialidades=especialidades
    )

# ============================================================
# OBTENER GRUPO DEL USUARIO
# ============================================================

def obtener_grupo_usuario(usuario_id):

    with conectar_db() as db:

        grupo = db.execute(
            """
            SELECT
                g.*,
                mg.es_lider
            FROM grupos g
            JOIN miembros_grupo mg
                ON mg.grupo_id = g.id
            WHERE mg.estudiante_id = ?
            AND mg.estado = 'activo'
            LIMIT 1
            """,
            (usuario_id,)
        ).fetchone()

    return grupo

# ============================================================
# OBTENER INVESTIGACIÓN DEL USUARIO
# ============================================================

def obtener_investigacion_usuario(usuario_id):

    # Primero obtenemos el grupo activo del estudiante
    grupo = obtener_grupo_usuario(usuario_id)

    if not grupo:
        return None

    # Buscamos la investigación correspondiente a ese grupo
    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE grupo_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (grupo["id"],)
        ).fetchone()

    return investigacion





@app.route("/panel")
@login_requerido
def panel():

    usuario = usuario_actual()

    # ========================================================
    # ADMINISTRADOR — CENTRO DE CONTROL CON DATOS REALES
    # ========================================================

    if usuario["rol"] == "admin":

        asegurar_columnas_permisos_biblioteca()

        with conectar_db() as db:

            # ------------------------------------------------
            # ESTADÍSTICAS GENERALES
            # ------------------------------------------------

            estadisticas = {
                "usuarios": db.execute("""
                    SELECT COUNT(*)
                    FROM usuarios
                    WHERE activo = 1
                """).fetchone()[0],

                "estudiantes": db.execute("""
                    SELECT COUNT(*)
                    FROM usuarios
                    WHERE rol = 'estudiante'
                      AND activo = 1
                """).fetchone()[0],

                "profesores": db.execute("""
                    SELECT COUNT(*)
                    FROM usuarios
                    WHERE rol = 'tutor'
                      AND activo = 1
                """).fetchone()[0],

                "grupos": db.execute("""
                    SELECT COUNT(*)
                    FROM grupos
                """).fetchone()[0],

                "investigaciones": db.execute("""
                    SELECT COUNT(*)
                    FROM investigaciones
                """).fetchone()[0],

                "finalizadas": db.execute("""
                    SELECT COUNT(*)
                    FROM investigaciones
                    WHERE finalizada = 1
                """).fetchone()[0],

                "entregas": db.execute("""
                    SELECT COUNT(*)
                    FROM entregas
                """).fetchone()[0],

                "revision": db.execute("""
                    SELECT COUNT(*)
                    FROM entregas
                    WHERE estado = 'Pendiente de revisión'
                """).fetchone()[0],

                "aprobadas": db.execute("""
                    SELECT COUNT(*)
                    FROM entregas
                    WHERE estado = 'Aprobado'
                """).fetchone()[0],

                "correcciones": db.execute("""
                    SELECT COUNT(*)
                    FROM entregas
                    WHERE estado = 'Necesita correcciones'
                """).fetchone()[0]
            }

            # ------------------------------------------------
            # ALERTAS ACADÉMICAS
            # ------------------------------------------------

            condicion_alerta = """
                i.profesor_id IS NULL
                OR EXISTS (
                    SELECT 1
                    FROM entregas AS e
                    WHERE e.investigacion_id = i.id
                      AND e.nivel = i.nivel_actual
                      AND e.estado = 'Necesita correcciones'
                )
            """

            total_alertas = db.execute(f"""
                SELECT COUNT(*)
                FROM investigaciones AS i
                WHERE {condicion_alerta}
            """).fetchone()[0]

            alertas_academicas = db.execute(f"""
                SELECT
                    i.id,
                    i.titulo,
                    i.nivel_actual,
                    i.estado,
                    g.nombre AS grupo_nombre,
                    t.nombre AS profesor_nombre,
                    t.apellido AS profesor_apellido,

                    CASE
                        WHEN i.profesor_id IS NULL
                             AND EXISTS (
                                SELECT 1
                                FROM entregas AS e
                                WHERE e.investigacion_id = i.id
                                  AND e.nivel = i.nivel_actual
                                  AND e.estado = 'Necesita correcciones'
                             )
                        THEN 'Sin tutor y con correcciones'

                        WHEN i.profesor_id IS NULL
                        THEN 'Sin tutor asignado'

                        ELSE 'Necesita correcciones'
                    END AS tipo_alerta,

                    (
                        SELECT COUNT(*)
                        FROM entregas AS e
                        WHERE e.investigacion_id = i.id
                          AND e.nivel = i.nivel_actual
                          AND e.estado = 'Necesita correcciones'
                    ) AS cantidad_correcciones,

                    (
                        SELECT COUNT(*)
                        FROM entregas AS e
                        WHERE e.investigacion_id = i.id
                          AND e.nivel = i.nivel_actual
                          AND e.estado = 'Pendiente de revisión'
                    ) AS cantidad_revision

                FROM investigaciones AS i

                INNER JOIN grupos AS g
                    ON g.id = i.grupo_id

                LEFT JOIN usuarios AS t
                    ON t.id = i.profesor_id

                WHERE {condicion_alerta}

                ORDER BY i.creado_en DESC
                LIMIT 8
            """).fetchall()

            # ------------------------------------------------
            # ÚLTIMO COMUNICADO
            # ------------------------------------------------

            ultimo_comunicado = db.execute("""
                SELECT
                    id,
                    titulo,
                    publicado_en
                FROM comunicados_institucionales
                WHERE activo = 1
                ORDER BY publicado_en DESC, id DESC
                LIMIT 1
            """).fetchone()

            # ------------------------------------------------
            # ÚLTIMA COPIA DE SEGURIDAD
            # ------------------------------------------------

            ultima_copia = db.execute("""
                SELECT
                    detalle,
                    creado_en
                FROM auditoria_tesislab
                WHERE accion = 'Generó respaldo'
                ORDER BY creado_en DESC, id DESC
                LIMIT 1
            """).fetchone()

            # ------------------------------------------------
            # EVENTOS DEL CRONOGRAMA
            # ------------------------------------------------

            eventos_cronograma = db.execute("""
                SELECT *
                FROM eventos_cronograma
                WHERE activa = 1
                ORDER BY fecha ASC, hora_inicio ASC, id ASC
            """).fetchall()

            # ------------------------------------------------
            # TUTORES Y PERMISOS DE BIBLIOTECA
            # ------------------------------------------------

            tutores_biblioteca = db.execute("""
                SELECT
                    u.id,
                    u.nombre,
                    u.apellido,
                    u.usuario,
                    COALESCE(p.puede_publicar, 0) AS puede_publicar,
                    COALESCE(p.puede_editar, 0) AS puede_editar,
                    COALESCE(p.puede_eliminar, 0) AS puede_eliminar,
                    COALESCE(p.puede_gestionar, 0) AS puede_gestionar
                FROM usuarios AS u
                LEFT JOIN permisos_biblioteca AS p
                    ON p.tutor_id = u.id
                WHERE u.rol = 'tutor'
                  AND u.activo = 1
                ORDER BY u.apellido, u.nombre
            """).fetchall()

            # ------------------------------------------------
            # ESTADÍSTICAS DE LOS SEIS NIVELES
            # ------------------------------------------------

            nombres_niveles = [
                "Presentación del tema",
                "Capítulo I",
                "Capítulo II",
                "Capítulo III",
                "Capítulo IV",
                "Capítulo V"
            ]

            capitulos = []

            total_investigaciones = estadisticas["investigaciones"]

            for numero, nombre in enumerate(nombres_niveles, start=1):

                presentadas = db.execute("""
                    SELECT COUNT(DISTINCT investigacion_id)
                    FROM entregas
                    WHERE nivel = ?
                """, (numero,)).fetchone()[0]

                aprobadas_nivel = db.execute("""
                    SELECT COUNT(DISTINCT investigacion_id)
                    FROM entregas
                    WHERE nivel = ?
                      AND estado = 'Aprobado'
                """, (numero,)).fetchone()[0]

                porcentaje = (
                    round(
                        aprobadas_nivel * 100 / total_investigaciones
                    )
                    if total_investigaciones else 0
                )

                capitulos.append({
                    "numero": numero,
                    "nombre": nombre,
                    "presentadas": presentadas,
                    "aprobadas": aprobadas_nivel,
                    "pendientes": max(
                        0,
                        total_investigaciones - presentadas
                    ),
                    "porcentaje": min(100, porcentaje)
                })

            # ------------------------------------------------
            # SEGUIMIENTO REAL DE INVESTIGACIONES
            # ------------------------------------------------

            investigaciones = db.execute("""
                SELECT
                    i.id,
                    i.titulo,
                    i.nivel_actual,
                    i.estado,
                    i.finalizada,
                    i.creado_en,

                    g.nombre AS grupo_nombre,

                    t.nombre AS profesor_nombre,
                    t.apellido AS profesor_apellido,

                    (
                        SELECT e.estado
                        FROM entregas AS e
                        WHERE e.investigacion_id = i.id
                          AND e.nivel = i.nivel_actual
                        ORDER BY e.id DESC
                        LIMIT 1
                    ) AS estado_entrega,

                    (
                        SELECT e.enviado_en
                        FROM entregas AS e
                        WHERE e.investigacion_id = i.id
                          AND e.nivel = i.nivel_actual
                        ORDER BY e.id DESC
                        LIMIT 1
                    ) AS fecha_entrega,

                    (
                        SELECT COUNT(DISTINCT e.nivel)
                        FROM entregas AS e
                        WHERE e.investigacion_id = i.id
                          AND e.estado = 'Aprobado'
                    ) AS niveles_aprobados,

                    ROUND(
                        (
                            SELECT COUNT(DISTINCT e.nivel)
                            FROM entregas AS e
                            WHERE e.investigacion_id = i.id
                              AND e.estado = 'Aprobado'
                        ) * 100.0 / 6
                    ) AS progreso

                FROM investigaciones AS i

                INNER JOIN grupos AS g
                    ON g.id = i.grupo_id

                LEFT JOIN usuarios AS t
                    ON t.id = i.profesor_id

                ORDER BY i.creado_en DESC
            """).fetchall()

            # ------------------------------------------------
            # PROPUESTAS DEL ADMINISTRADOR A LOS TUTORES
            # ------------------------------------------------

            propuestas_enviadas = db.execute("""
                SELECT
                    s.id AS solicitud_id,
                    s.estado,
                    s.creado_en,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo_nombre,
                    t.nombre AS tutor_nombre,
                    t.apellido AS tutor_apellido
                FROM solicitudes_asignacion AS s
                JOIN investigaciones AS i
                    ON i.id = s.investigacion_id
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                JOIN usuarios AS t
                    ON t.id = s.tutor_id
                WHERE s.tipo = 'admin_a_tutor'
                  AND s.estado = 'Pendiente'
                ORDER BY s.creado_en DESC
            """).fetchall()

            # ------------------------------------------------
            # SOLICITUDES DE LOS TUTORES AL ADMINISTRADOR
            # ------------------------------------------------

            solicitudes_tutores = db.execute("""
                SELECT
                    s.id AS solicitud_id,
                    s.estado,
                    s.creado_en,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo_nombre,
                    t.nombre AS tutor_nombre,
                    t.apellido AS tutor_apellido
                FROM solicitudes_asignacion AS s
                JOIN investigaciones AS i
                    ON i.id = s.investigacion_id
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                JOIN usuarios AS t
                    ON t.id = s.tutor_id
                WHERE s.tipo = 'tutor_a_admin'
                  AND s.estado = 'Pendiente'
                ORDER BY s.creado_en DESC
            """).fetchall()

        return render_template(
            "panel_admin.html",
            usuario=usuario,
            estadisticas=estadisticas,
            investigaciones=investigaciones,
            capitulos=capitulos,
            tutores_biblioteca=tutores_biblioteca,
            propuestas_enviadas=propuestas_enviadas,
            solicitudes_tutores=solicitudes_tutores,
            eventos_cronograma=eventos_cronograma,
            total_usuarios=estadisticas["usuarios"],
            total_investigaciones=estadisticas["investigaciones"],
            total_temas=estadisticas["investigaciones"],
            total_alertas=total_alertas,
            alertas_academicas=alertas_academicas,
            ultimo_comunicado=ultimo_comunicado,
            ultima_copia=ultima_copia,
            total_entregas_revision=estadisticas["revision"]
        )
       
    # ========================================================
    # PROFESOR / TUTOR
    # ========================================================

    if usuario["rol"] == "tutor":

        with conectar_db() as db:

            # INVESTIGACIONES ASIGNADAS AL TUTOR

            investigaciones = db.execute("""
                SELECT
                    i.*,
                    g.nombre AS grupo_nombre
                FROM investigaciones AS i
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                ORDER BY i.creado_en DESC
            """, (usuario["id"],)).fetchall()

            # TEMAS SIN TUTOR ASIGNADO

            temas_disponibles = db.execute("""
                SELECT
                    i.*,
                    g.nombre AS grupo_nombre
                FROM investigaciones AS i
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id IS NULL
                ORDER BY i.creado_en DESC
            """).fetchall()

            # PROPUESTAS DEL ADMINISTRADOR PARA ESTE TUTOR

            propuestas_asignacion = db.execute("""
                SELECT
                    s.id AS solicitud_id,
                    s.creado_en,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo_nombre
                FROM solicitudes_asignacion AS s
                JOIN investigaciones AS i
                    ON i.id = s.investigacion_id
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                WHERE s.tutor_id = ?
                  AND s.tipo = 'admin_a_tutor'
                  AND s.estado = 'Pendiente'
                ORDER BY s.creado_en DESC
            """, (usuario["id"],)).fetchall()

            # ENTREGAS PENDIENTES DE REVISIÓN
            # INCLUYE LOS DATOS PARA COMPARAR VERSIONES

            entregas_pendientes = db.execute("""
                SELECT
                    e.id AS entrega_id,
                    e.investigacion_id,
                    e.nivel,
                    e.estado,
                    e.enviado_en,
                    i.titulo,
                    g.nombre AS grupo_nombre,

                    (
                        SELECT h.id
                        FROM historial_entregas AS h
                        WHERE h.entrega_id = e.id
                        ORDER BY h.version DESC
                        LIMIT 1
                    ) AS historial_actual_id,

                    (
                        SELECT h.version
                        FROM historial_entregas AS h
                        WHERE h.entrega_id = e.id
                        ORDER BY h.version DESC
                        LIMIT 1
                    ) AS version_actual,

                    (
                        SELECT COUNT(*)
                        FROM historial_entregas AS h
                        WHERE h.entrega_id = e.id
                    ) AS total_versiones

                FROM entregas AS e
                JOIN investigaciones AS i
                    ON i.id = e.investigacion_id
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                  AND i.finalizada = 0
                  AND e.estado = 'Pendiente de revisión'
                ORDER BY e.enviado_en ASC, e.id ASC
            """, (usuario["id"],)).fetchall()

            # PRÓXIMAS REUNIONES DEL TUTOR

            proximas_reuniones = db.execute("""
                SELECT
                    sr.id AS reunion_id,
                    sr.motivo,
                    sr.fecha_solicitada,
                    sr.hora_solicitada,
                    sr.duracion,
                    sr.estado,
                    sr.enlace_meet,
                    sr.estudiante_id,
                    i.id AS investigacion_id,
                    i.titulo AS investigacion_titulo,
                    g.nombre AS grupo_nombre,
                    u.nombre AS estudiante_nombre,
                    u.apellido AS estudiante_apellido
                FROM solicitudes_reunion AS sr
                JOIN investigaciones AS i
                    ON i.id = sr.investigacion_id
                JOIN grupos AS g
                    ON g.id = i.grupo_id
                JOIN usuarios AS u
                    ON u.id = sr.estudiante_id
                WHERE i.profesor_id = ?
                  AND date(sr.fecha_solicitada) >= date('now', 'localtime')
                  AND sr.estado IN (
                      'Aceptada',
                      'Pendiente',
                      'Nueva propuesta'
                  )
                ORDER BY
                    sr.fecha_solicitada ASC,
                    sr.hora_solicitada ASC
                LIMIT 5
            """, (usuario["id"],)).fetchall()

        return render_template(
            "panel_tutor.html",
            usuario=usuario,
            investigaciones=investigaciones,
            temas_disponibles=temas_disponibles,
            propuestas_asignacion=propuestas_asignacion,
            entregas_pendientes=entregas_pendientes,
            proximas_reuniones=proximas_reuniones
        )

    # ========================================================
    # ESTUDIANTE
    # ========================================================

    investigacion = obtener_investigacion_usuario(usuario["id"])
    grupo = obtener_grupo_usuario(usuario["id"])

    tareas_pendientes = 0
    progreso_porcentaje = 0
    capitulos_completados = 0
    entregas_pendientes = 0

    siguiente_entrega = None
    fecha_siguiente = None
    fecha_mensaje = "Sin investigación asignada"

    semaforo_entregas = []
    proximas_fechas = []
    tareas_estudiante = []

    if investigacion:

        investigacion_id = investigacion["id"]
        hoy = date.today()

        with conectar_db() as db:

            # TAREAS PENDIENTES

            tareas_estudiante = db.execute("""
                SELECT
                    id,
                    titulo,
                    descripcion,
                    fecha_limite,
                    completada
                FROM tareas
                WHERE investigacion_id = ?
                  AND completada = 0
                ORDER BY
                    CASE
                        WHEN fecha_limite IS NULL
                          OR TRIM(fecha_limite) = ''
                        THEN 1
                        ELSE 0
                    END,
                    fecha_limite ASC
            """, (investigacion_id,)).fetchall()

            tareas_pendientes = len(tareas_estudiante)

            # NIVELES APROBADOS

            niveles_aprobados = db.execute("""
                SELECT COUNT(DISTINCT nivel)
                FROM entregas
                WHERE investigacion_id = ?
                  AND estado = 'Aprobado'
            """, (investigacion_id,)).fetchone()[0]

            progreso_porcentaje = round(
                (niveles_aprobados / 6) * 100
            )

            # CAPÍTULOS COMPLETADOS — NIVELES 2 AL 6

            capitulos_completados = db.execute("""
                SELECT COUNT(DISTINCT nivel)
                FROM entregas
                WHERE investigacion_id = ?
                  AND nivel BETWEEN 2 AND 6
                  AND estado = 'Aprobado'
            """, (investigacion_id,)).fetchone()[0]

            # ENTREGAS PENDIENTES

            entregas_pendientes = db.execute("""
                SELECT COUNT(*)
                FROM entregas
                WHERE investigacion_id = ?
                  AND estado IN (
                      'Pendiente',
                      'Pendiente de revisión',
                      'Necesita correcciones'
                  )
            """, (investigacion_id,)).fetchone()[0]

            # ÚLTIMA ENTREGA DE CADA NIVEL

            entregas = db.execute("""
                SELECT
                    e.id,
                    e.nivel,
                    e.estado,
                    e.enviado_en,
                    e.revisado_en,
                    e.comentario_profesor
                FROM entregas AS e
                WHERE e.investigacion_id = ?
                  AND e.id = (
                      SELECT MAX(e2.id)
                      FROM entregas AS e2
                      WHERE e2.investigacion_id = e.investigacion_id
                        AND e2.nivel = e.nivel
                  )
                ORDER BY e.nivel ASC
            """, (investigacion_id,)).fetchall()

            nombres_niveles = {
                1: "Presentación del tema",
                2: "Capítulo I",
                3: "Capítulo II",
                4: "Capítulo III",
                5: "Capítulo IV",
                6: "Capítulo V"
            }

            for entrega in entregas:

                estado = entrega["estado"] or "Pendiente"

                if estado == "Aprobado":
                    clase = "aprobado"
                    etiqueta = "Aprobado"

                elif estado == "Necesita correcciones":
                    clase = "correccion"
                    etiqueta = "Observado"

                elif estado == "Pendiente de revisión":
                    clase = "pendiente"
                    etiqueta = "En revisión"

                else:
                    clase = "pendiente"
                    etiqueta = "Pendiente"

                semaforo_entregas.append({
                    "titulo": nombres_niveles.get(
                        entrega["nivel"],
                        f"Nivel {entrega['nivel']}"
                    ),
                    "nivel": entrega["nivel"],
                    "estado": estado,
                    "etiqueta": etiqueta,
                    "clase": clase,
                    "fecha": entrega["enviado_en"],
                    "observaciones": entrega["comentario_profesor"]
                })

            # PRÓXIMA TAREA

            tareas_con_fecha = []

            for tarea in tareas_estudiante:

                fecha_texto = tarea["fecha_limite"]

                if not fecha_texto:
                    continue

                try:
                    fecha_objeto = date.fromisoformat(
                        str(fecha_texto)[:10]
                    )
                except (ValueError, TypeError):
                    continue

                tareas_con_fecha.append((
                    fecha_objeto,
                    tarea
                ))

                # TAREAS VENCIDAS EN EL SEMÁFORO

                if fecha_objeto < hoy:

                    semaforo_entregas.append({
                        "titulo": tarea["titulo"],
                        "nivel": None,
                        "estado": "Fecha vencida",
                        "etiqueta": "Vencida",
                        "clase": "vencido",
                        "fecha": fecha_texto,
                        "observaciones": tarea["descripcion"]
                    })

            tareas_con_fecha.sort(
                key=lambda elemento: elemento[0]
            )

            if tareas_con_fecha:

                fecha_objeto, siguiente_entrega = tareas_con_fecha[0]

                fecha_siguiente = fecha_objeto.strftime("%d %b")

                diferencia = (fecha_objeto - hoy).days

                if diferencia < 0:
                    fecha_mensaje = (
                        f"Vencida hace {abs(diferencia)} días"
                    )

                elif diferencia == 0:
                    fecha_mensaje = "Entrega para hoy"

                elif diferencia == 1:
                    fecha_mensaje = "Entrega mañana"

                else:
                    fecha_mensaje = f"En {diferencia} días"

            else:
                fecha_mensaje = "No tienes tareas con fecha pendiente"

            # PRÓXIMAS FECHAS: TAREAS

            for fecha_objeto, tarea in tareas_con_fecha:

                if fecha_objeto >= hoy:

                    proximas_fechas.append({
                        "fecha": fecha_objeto,
                        "dia": fecha_objeto.strftime("%d"),
                        "mes": fecha_objeto.strftime("%b").upper(),
                        "titulo": tarea["titulo"],
                        "detalle": "Tarea pendiente",
                        "tipo": "Tarea"
                    })

            # PRÓXIMAS FECHAS: REUNIONES

            reuniones = db.execute("""
                SELECT
                    id,
                    motivo,
                    fecha_solicitada,
                    hora_solicitada,
                    duracion,
                    estado,
                    enlace_meet
                FROM solicitudes_reunion
                WHERE investigacion_id = ?
                  AND estudiante_id = ?
                  AND estado IN (
                      'Aceptada',
                      'Pendiente',
                      'Nueva propuesta'
                  )
                  AND date(fecha_solicitada) >= date('now', 'localtime')
                ORDER BY
                    fecha_solicitada ASC,
                    hora_solicitada ASC
                LIMIT 10
            """, (investigacion_id, usuario["id"])).fetchall()

            for reunion in reuniones:

                try:
                    fecha_objeto = date.fromisoformat(
                        str(reunion["fecha_solicitada"])[:10]
                    )
                except (ValueError, TypeError):
                    continue

                proximas_fechas.append({
                    "fecha": fecha_objeto,
                    "dia": fecha_objeto.strftime("%d"),
                    "mes": fecha_objeto.strftime("%b").upper(),
                    "titulo": reunion["motivo"],
                    "detalle": (
                        f"{reunion['hora_solicitada']} · "
                        f"{reunion['duracion']} minutos"
                    ),
                    "tipo": reunion["estado"]
                })

            # ORDENAR Y LIMITAR PRÓXIMAS FECHAS

            proximas_fechas.sort(
                key=lambda elemento: elemento["fecha"]
            )

            proximas_fechas = proximas_fechas[:5]

            # ORDENAR SEMÁFORO

            semaforo_entregas = semaforo_entregas[:8]

    # ========================================================
    # PANEL DEL ESTUDIANTE
    # ========================================================

    return render_template(
        "panel_estudiante.html",
        usuario=usuario,
        investigacion=investigacion,
        grupo=grupo,
        tareas_pendientes=tareas_pendientes,
        tareas_estudiante=tareas_estudiante,
        progreso_porcentaje=progreso_porcentaje,
        capitulos_completados=capitulos_completados,
        entregas_pendientes=entregas_pendientes,
        siguiente_entrega=siguiente_entrega,
        fecha_siguiente=fecha_siguiente,
        fecha_mensaje=fecha_mensaje,
        semaforo_entregas=semaforo_entregas,
        proximas_fechas=proximas_fechas
    )





# ============================================================
# GRUPOS A CARGO DEL TUTOR
# ============================================================

@app.route("/grupos-a-cargo")
@login_requerido
def grupos_a_cargo():

    usuario = usuario_actual()

    # Solo los tutores pueden acceder a esta página.

    if usuario["rol"] != "tutor":

        flash(
            "No tienes permiso para acceder a esta sección.",
            "error"
        )

        return redirect(url_for("panel"))

    with conectar_db() as db:

        grupos_a_cargo = db.execute("""
            SELECT
                g.id,
                g.nombre AS grupo_nombre,
                i.id AS investigacion_id,
                i.titulo AS investigacion_titulo,
                i.area_principal,
                i.subarea,

                (
                    SELECT TRIM(
                        u.nombre || ' ' ||
                        COALESCE(u.apellido, '')
                    )
                    FROM usuarios u
                    WHERE u.id = g.lider_id
                ) AS lider_nombre,

                (
                    SELECT COUNT(*)
                    FROM miembros_grupo mg
                    WHERE mg.grupo_id = g.id
                      AND mg.estado = 'activo'
                ) AS cantidad_miembros,

                (
                    SELECT GROUP_CONCAT(nombre_completo, ', ')
                    FROM (
                        SELECT TRIM(
                            u.nombre || ' ' ||
                            COALESCE(u.apellido, '')
                        ) AS nombre_completo
                        FROM miembros_grupo mg
                        JOIN usuarios u
                            ON u.id = mg.estudiante_id
                        WHERE mg.grupo_id = g.id
                          AND mg.estado = 'activo'
                        ORDER BY mg.es_lider DESC, u.apellido, u.nombre
                    )
                ) AS integrantes

            FROM investigaciones i
            JOIN grupos g
                ON g.id = i.grupo_id

            WHERE i.profesor_id = ?

            ORDER BY g.nombre ASC
        """, (usuario["id"],)).fetchall()

    return render_template(
        "grupos_a_cargo.html",
        usuario=usuario,
        grupos_a_cargo=grupos_a_cargo
    )


# ============================================================
# MIS ESTADÍSTICAS DEL TUTOR
# ============================================================

@app.route("/mis-estadisticas")
@roles_requeridos("admin", "tutor")
def mis_estadisticas():

    usuario = usuario_actual()
    tutor_id = usuario["id"]

    with conectar_db() as db:

        # 1. ENTREGAS REVISADAS Y NOTA PROMEDIO
        resumen = db.execute("""
            SELECT
                COUNT(*) AS entregas_revisadas,
                ROUND(AVG(puntaje_total), 1) AS nota_promedio
            FROM rubricas_evaluaciones
            WHERE evaluador_id = ?
        """, (tutor_id,)).fetchone()

        entregas_revisadas = resumen["entregas_revisadas"] or 0
        nota_promedio = resumen["nota_promedio"]

        # 2. DÍAS PROMEDIO DE REVISIÓN
        revision = db.execute("""
            SELECT ROUND(AVG(
                julianday(h.revisado_en) -
                julianday(h.enviado_en)
            ), 1) AS dias_promedio
            FROM rubricas_evaluaciones r
            JOIN historial_entregas h
                ON h.id = r.historial_entrega_id
            WHERE r.evaluador_id = ?
              AND h.revisado_en IS NOT NULL
              AND h.enviado_en IS NOT NULL
        """, (tutor_id,)).fetchone()

        dias_promedio = revision["dias_promedio"]

        # 3. APROBADAS A LA PRIMERA
        primera = db.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN h.version = 1
                         AND h.estado = 'Aprobado'
                        THEN 1
                        ELSE 0
                    END
                ) AS aprobadas
            FROM rubricas_evaluaciones r
            JOIN historial_entregas h
                ON h.id = r.historial_entrega_id
            WHERE r.evaluador_id = ?
        """, (tutor_id,)).fetchone()

        total_evaluadas = primera["total"] or 0
        aprobadas_primera = primera["aprobadas"] or 0

        porcentaje_primera = (
            round((aprobadas_primera / total_evaluadas) * 100)
            if total_evaluadas > 0 else 0
        )

        # 4. GRUPOS POR NIVEL
        grupos_nivel = db.execute("""
            SELECT
                nivel_actual,
                COUNT(*) AS cantidad
            FROM investigaciones
            WHERE profesor_id = ?
            GROUP BY nivel_actual
            ORDER BY nivel_actual
        """, (tutor_id,)).fetchall()

        cantidades_nivel = {
            fila["nivel_actual"]: fila["cantidad"]
            for fila in grupos_nivel
        }

        # 5. CRITERIOS CON MAYORES DIFICULTADES
        criterios = db.execute("""
            SELECT
                d.criterio_nombre,
                ROUND(
                    AVG(
                        100.0 * d.puntaje_obtenido /
                        NULLIF(d.puntaje_maximo, 0)
                    ), 0
                ) AS porcentaje
            FROM rubricas_detalle d
            JOIN rubricas_evaluaciones r
                ON r.id = d.evaluacion_id
            WHERE r.evaluador_id = ?
              AND d.puntaje_maximo > 0
            GROUP BY d.criterio_nombre
            ORDER BY porcentaje ASC
        """, (tutor_id,)).fetchall()

        # 6. TUTORÍAS ACEPTADAS
        tutorias = db.execute("""
            SELECT COUNT(*) AS cantidad
            FROM solicitudes_reunion
            WHERE estado = 'Aceptada'
              AND investigacion_id IN (
                  SELECT id
                  FROM investigaciones
                  WHERE profesor_id = ?
              )
        """, (tutor_id,)).fetchone()

    return render_template(
        "estadisticas.html",
        usuario=usuario,
        entregas_revisadas=entregas_revisadas,
        nota_promedio=nota_promedio,
        dias_promedio=dias_promedio,
        porcentaje_primera=porcentaje_primera,
        tutorias_registradas=tutorias["cantidad"] or 0,
        cantidades_nivel=cantidades_nivel,
        criterios=criterios
    )


# ============================================================
# SEGUIMIENTO DE GRUPOS
# ============================================================

@app.route("/seguimiento-grupos")
@roles_requeridos("admin", "tutor")
def seguimiento_grupos():

    usuario = usuario_actual()

    with conectar_db() as db:

        if usuario["rol"] == "admin":

            grupos = db.execute("""
                SELECT
                    g.id AS grupo_id,
                    g.nombre AS grupo_nombre,
                    i.id AS investigacion_id,
                    i.titulo AS investigacion_titulo,
                    i.nivel_actual,
                    i.estado,
                    i.creado_en,

                    (
                        SELECT COUNT(*)
                        FROM niveles_investigacion ni
                        WHERE ni.investigacion_id = i.id
                          AND ni.estado = 'Aprobado'
                    ) AS niveles_aprobados,

                    (
                        SELECT COUNT(*)
                        FROM niveles_investigacion ni
                        WHERE ni.investigacion_id = i.id
                          AND ni.estado = 'Necesita correcciones'
                    ) AS niveles_con_correcciones,

                    (
                        SELECT COUNT(*)
                        FROM entregas e
                        WHERE e.investigacion_id = i.id
                          AND e.estado = 'Necesita correcciones'
                    ) AS entregas_con_correcciones,

                    (
                        SELECT MAX(fecha)
                        FROM (
                            SELECT enviado_en AS fecha
                            FROM entregas
                            WHERE investigacion_id = i.id

                            UNION ALL

                            SELECT i.enviado_en AS fecha
                            FROM historial_entregas
                            WHERE investigacion_id = i.id

                            UNION ALL

                            SELECT i.creado_en AS fecha
                        )
                    ) AS ultima_actividad

                FROM investigaciones i

                JOIN grupos g
                    ON g.id = i.grupo_id

                WHERE i.finalizada = 0

                ORDER BY g.nombre ASC

            """).fetchall()

        else:

            grupos = db.execute("""
                SELECT
                    g.id AS grupo_id,
                    g.nombre AS grupo_nombre,
                    i.id AS investigacion_id,
                    i.titulo AS investigacion_titulo,
                    i.nivel_actual,
                    i.estado,
                    i.creado_en,

                    (
                        SELECT COUNT(*)
                        FROM niveles_investigacion ni
                        WHERE ni.investigacion_id = i.id
                          AND ni.estado = 'Aprobado'
                    ) AS niveles_aprobados,

                    (
                        SELECT COUNT(*)
                        FROM niveles_investigacion ni
                        WHERE ni.investigacion_id = i.id
                          AND ni.estado = 'Necesita correcciones'
                    ) AS niveles_con_correcciones,

                    (
                        SELECT COUNT(*)
                        FROM entregas e
                        WHERE e.investigacion_id = i.id
                          AND e.estado = 'Necesita correcciones'
                    ) AS entregas_con_correcciones,
                    (
                    SELECT MAX(fecha)
                    FROM (
                    SELECT e.enviado_en AS fecha
                    FROM entregas e
                    WHERE e.investigacion_id = i.id

                    UNION ALL

                    SELECT h.enviado_en AS fecha
                    FROM historial_entregas h
                    WHERE h.investigacion_id = i.id

                    UNION ALL

                    SELECT i.creado_en AS fecha
                    )
                ) AS ultima_actividad

                FROM investigaciones i

                JOIN grupos g
                    ON g.id = i.grupo_id

                WHERE i.profesor_id = ?
                  AND i.finalizada = 0

                ORDER BY g.nombre ASC

            """, (usuario["id"],)).fetchall()

    # Preparar información para la pantalla.
    grupos_seguimiento = []

    for grupo in grupos:

        aprobados = grupo["niveles_aprobados"] or 0

        # El proyecto tiene 6 niveles.
        avance = round((aprobados / 6) * 100)

        necesita_apoyo = (
            (grupo["niveles_con_correcciones"] or 0) > 0
            or (grupo["entregas_con_correcciones"] or 0) > 0
        )

        alerta = (
            "Apoyo prioritario"
            if necesita_apoyo
            else "Sin alertas"
        )

        grupos_seguimiento.append({
            "grupo_id": grupo["grupo_id"],
            "grupo_nombre": grupo["grupo_nombre"],
            "investigacion_id": grupo["investigacion_id"],
            "investigacion_titulo": grupo["investigacion_titulo"],
            "nivel_actual": grupo["nivel_actual"],
            "avance": avance,
            "ultima_actividad": grupo["ultima_actividad"],
            "alerta": alerta
        })

    return render_template(
        "seguimiento_grupos.html",
        usuario=usuario,
        grupos_seguimiento=grupos_seguimiento
    )


# ============================================================
# REVISOR DE ESTRUCTURA: INVESTIGACIONES DISPONIBLES
# ============================================================

@app.route("/innovaciones/tutor/revisor-estructura")
@roles_requeridos("admin", "tutor")
def seleccionar_investigacion_revisor():

    usuario = usuario_actual()

    with conectar_db() as db:

        if usuario["rol"] == "admin":

            investigaciones_revisor = db.execute("""
                SELECT
                    i.id,
                    i.titulo,
                    i.area_principal,
                    i.subarea,
                    g.nombre AS grupo_nombre
                FROM investigaciones i
                LEFT JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.finalizada = 0
                ORDER BY i.titulo ASC
            """).fetchall()

        else:

            investigaciones_revisor = db.execute("""
                SELECT
                    i.id,
                    i.titulo,
                    i.area_principal,
                    i.subarea,
                    g.nombre AS grupo_nombre
                FROM investigaciones i
                LEFT JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                  AND i.finalizada = 0
                ORDER BY i.titulo ASC
            """, (usuario["id"],)).fetchall()

    return render_template(
        "seleccionar_investigacion_revisor.html",
        usuario=usuario,
        investigaciones_revisor=investigaciones_revisor
    )


# ============================================================
# GRUPOS
# ============================================================

@app.route("/grupos", methods=["GET", "POST"])
@login_requerido
def grupos():

    usuario = usuario_actual()

    # ========================================================
    # VISTA ADMINISTRADOR Y PROFESOR
    # ========================================================

    if usuario["rol"] != "estudiante":

        with conectar_db() as db:

            
            # CATÁLOGO GENERAL DE INVESTIGACIONES

            buscar = request.args.get("buscar", "").strip()
            filtro = f"%{buscar}%"

            catalogo_investigaciones = db.execute("""
                SELECT
                    i.id,
                    i.titulo,
                    i.profesor_id,
                    i.area_principal,
                    i.subarea,
                    g.nombre AS grupo_nombre,
                    t.nombre AS tutor_nombre,
                    t.apellido AS tutor_apellido,

                    (
                        SELECT s.id
                        FROM solicitudes_asignacion AS s
                        WHERE s.investigacion_id = i.id
                          AND s.tutor_id = ?
                          AND s.tipo = 'admin_a_tutor'
                          AND s.estado = 'Pendiente'
                        ORDER BY s.creado_en DESC
                        LIMIT 1
                    ) AS propuesta_id

                FROM investigaciones AS i

                JOIN grupos AS g
                    ON g.id = i.grupo_id

                LEFT JOIN usuarios AS t
                    ON t.id = i.profesor_id

                WHERE (
                    ? = ''
                    OR i.titulo LIKE ?
                    OR g.nombre LIKE ?
                    OR COALESCE(t.nombre, '') LIKE ?
                    OR COALESCE(t.apellido, '') LIKE ?
                )

                ORDER BY i.creado_en DESC
            """, (
                usuario["id"],
                buscar,
                filtro,
                filtro,
                filtro,
                filtro
            )).fetchall()
            grupos_lista = db.execute(
        """
        SELECT
            g.id,
            g.nombre,
            g.lider_id,

            (
                SELECT TRIM(
                    COALESCE(t.nombre, '') || ' ' ||
                    COALESCE(t.apellido, '')
                )
                FROM investigaciones i
                LEFT JOIN usuarios t
                    ON t.id = i.profesor_id
                WHERE i.grupo_id = g.id
                ORDER BY i.creado_en DESC
                LIMIT 1
            ) AS tutor_nombre,

            (
                SELECT i.titulo
                FROM investigaciones i
                WHERE i.grupo_id = g.id
                ORDER BY i.creado_en DESC
                LIMIT 1
            ) AS investigacion_titulo,

            (
                SELECT COUNT(*)
                FROM miembros_grupo mg
                WHERE mg.grupo_id = g.id
                AND mg.estado = 'activo'
            ) AS cantidad_miembros,

            (
                SELECT GROUP_CONCAT(
                    TRIM(
                        u.nombre || ' ' ||
                        COALESCE(u.apellido, '')
                    ),
                    '|'
                )
                FROM miembros_grupo mg
                JOIN usuarios u
                    ON u.id = mg.estudiante_id
                WHERE mg.grupo_id = g.id
                AND mg.estado = 'activo'
            ) AS integrantes

            FROM grupos g
            ORDER BY g.creado_en DESC
            """
        ).fetchall()

        if usuario["rol"] == "admin":
                return render_template(
                    "gestionar_grupos.html",
                    usuario=usuario,
                    grupos=grupos_lista
                )

        return render_template(
                "grupos.html",
                usuario=usuario,
                grupos=grupos_lista,
                catalogo_investigaciones=catalogo_investigaciones
            )
    # ========================================================
    # OBTENER GRUPO DEL ESTUDIANTE
    # ========================================================

    grupo = obtener_grupo_usuario(usuario["id"])

    # ========================================================
    # CREAR GRUPO AUTOMÁTICAMENTE
    # ========================================================

    if request.method == "POST":

        if grupo:

            flash(
                "Ya perteneces a un grupo.",
                "error"
            )

            return redirect(url_for("grupos"))

        with conectar_db() as db:

            cursor = db.execute(
                """
                INSERT INTO grupos (nombre, lider_id)
                VALUES (?, ?)
                """,
                (
                    "Grupo temporal",
                    usuario["id"]
                )
            )

            grupo_id = cursor.lastrowid
            nombre_grupo = f"Grupo {grupo_id}"

            db.execute(
                """
                UPDATE grupos
                SET nombre = ?
                WHERE id = ?
                """,
                (
                    nombre_grupo,
                    grupo_id
                )
            )

            db.execute(
                """
                INSERT INTO miembros_grupo
                (
                    grupo_id,
                    estudiante_id,
                    es_lider,
                    estado
                )
                VALUES (?, ?, 1, 'activo')
                """,
                (
                    grupo_id,
                    usuario["id"]
                )
            )

        flash(
            f"¡Bienvenido al {nombre_grupo}! "
            "Puedes invitar hasta dos estudiantes más.",
            "exito"
        )

        return redirect(url_for("grupos"))

    # ========================================================
    # DATOS INICIALES
    # ========================================================

    miembros = []
    invitaciones = []
    estudiantes_disponibles = []

    # ========================================================
    # CONSULTA REUTILIZABLE PARA LAS INVITACIONES
    # MUESTRA LÍDER, INTEGRANTES Y CUPOS OCUPADOS
    # ========================================================

    consulta_invitaciones = """
        SELECT
            ig.*,
            g.nombre AS grupo_nombre,

            (
                SELECT TRIM(
                    u.nombre || ' ' ||
                    COALESCE(u.apellido, '')
                )
                FROM usuarios u
                WHERE u.id = g.lider_id
            ) AS lider_nombre,

            (
                SELECT GROUP_CONCAT(
                    TRIM(
                        u.nombre || ' ' ||
                        COALESCE(u.apellido, '')
                    ),
                    ', '
                )
                FROM miembros_grupo mg
                JOIN usuarios u
                    ON u.id = mg.estudiante_id
                WHERE mg.grupo_id = g.id
                  AND mg.estado = 'activo'
            ) AS integrantes_nombres,

            (
                SELECT COUNT(*)
                FROM miembros_grupo mg
                WHERE mg.grupo_id = g.id
                  AND mg.estado = 'activo'
            ) AS cantidad_miembros

        FROM invitaciones_grupo ig
        JOIN grupos g
            ON g.id = ig.grupo_id
        WHERE ig.invitado_id = ?
          AND ig.estado = 'pendiente'
        ORDER BY ig.creado_en DESC
    """

    # ========================================================
    # SI EL ESTUDIANTE YA PERTENECE A UN GRUPO
    # ========================================================

    if grupo:

        with conectar_db() as db:

            # Obtener integrantes activos del grupo propio.

            miembros = db.execute(
                """
                SELECT
                    u.id,
                    u.nombre,
                    u.apellido,
                    u.usuario,
                    mg.es_lider
                FROM miembros_grupo mg
                JOIN usuarios u
                    ON u.id = mg.estudiante_id
                WHERE mg.grupo_id = ?
                  AND mg.estado = 'activo'
                ORDER BY
                    mg.es_lider DESC,
                    u.apellido,
                    u.nombre
                """,
                (grupo["id"],)
            ).fetchall()

            # Obtener invitaciones pendientes recibidas,
            # con los nombres de los integrantes del otro grupo.

            invitaciones = db.execute(
                consulta_invitaciones,
                (usuario["id"],)
            ).fetchall()

            # Solo el líder puede invitar estudiantes.
            # Máximo: tres integrantes por grupo.

            if grupo["es_lider"]:

                cantidad = db.execute(
                    """
                    SELECT COUNT(*)
                    FROM miembros_grupo
                    WHERE grupo_id = ?
                      AND estado = 'activo'
                    """,
                    (grupo["id"],)
                ).fetchone()[0]

                if cantidad < 3:

                    estudiantes_disponibles = db.execute(
                        """
                        SELECT
                            u.id,
                            u.nombre,
                            u.apellido,
                            u.usuario
                        FROM usuarios u
                        WHERE u.rol = 'estudiante'
                          AND u.activo = 1
                          AND u.id != ?
                          AND u.id NOT IN
                          (
                              SELECT estudiante_id
                              FROM miembros_grupo
                              WHERE estado = 'activo'
                          )
                        ORDER BY
                            u.apellido,
                            u.nombre
                        """,
                        (usuario["id"],)
                    ).fetchall()

    # ========================================================
    # SI TODAVÍA NO PERTENECE A UN GRUPO
    # ========================================================

    else:

        with conectar_db() as db:

            invitaciones = db.execute(
                consulta_invitaciones,
                (usuario["id"],)
            ).fetchall()

    # ========================================================
    # MOSTRAR PÁGINA DE GRUPOS
    # ========================================================

    return render_template(
        "grupos.html",
        usuario=usuario,
        grupo=grupo,
        miembros=miembros,
        invitaciones=invitaciones,
        estudiantes_disponibles=estudiantes_disponibles
    )

# ============================================================
# CATÁLOGO ACADÉMICO — TESIS LAB
# ============================================================

@app.route("/catalogo-academico", methods=["GET"])
@login_requerido
def catalogo_academico():

    usuario = usuario_actual()

    # El catálogo está destinado a tutores y administradores.
    if usuario["rol"] == "estudiante":
        flash(
            "El catálogo académico está disponible para tutores y administradores.",
            "error"
        )
        return redirect(url_for("grupos"))

    buscar = request.args.get("buscar", "").strip()
    filtro = f"%{buscar}%"
    area_seleccionada = request.args.get("area", "").strip()

    with conectar_db() as db:

        catalogo_investigaciones = db.execute("""
            SELECT
                i.id,
                i.titulo,
                i.profesor_id,
                i.area_principal,
                i.subarea,
                g.nombre AS grupo_nombre,
                (
                SELECT GROUP_CONCAT(
                TRIM(u.nombre || ' ' || COALESCE(u.apellido, '')),
                ', '
                )
                FROM miembros_grupo mg
                JOIN usuarios u ON u.id = mg.estudiante_id
                WHERE mg.grupo_id = i.grupo_id
                AND mg.estado = 'activo'
                ) AS integrantes,
                t.nombre AS tutor_nombre,
                t.apellido AS tutor_apellido,

                (
                    SELECT s.id
                    FROM solicitudes_asignacion AS s
                    WHERE s.investigacion_id = i.id
                      AND s.tutor_id = ?
                      AND s.tipo = 'admin_a_tutor'
                      AND s.estado = 'Pendiente'
                    ORDER BY s.creado_en DESC
                    LIMIT 1
                ) AS propuesta_id

            FROM investigaciones AS i

            JOIN grupos AS g
                ON g.id = i.grupo_id

            LEFT JOIN usuarios AS t
                ON t.id = i.profesor_id

           WHERE (
            ? = ''
            OR i.titulo LIKE ?
            OR g.nombre LIKE ?
            OR COALESCE(t.nombre, '') LIKE ?
            OR COALESCE(t.apellido, '') LIKE ?
            )   

            AND (
            ? = ''
            OR i.area_principal = ?
            )

            ORDER BY i.creado_en DESC
            """, (
            usuario["id"],
            buscar,
            filtro,
            filtro,
            filtro,
            filtro,
            area_seleccionada,
            area_seleccionada
        )).fetchall()

    return render_template(
        "catalogo_academico.html",
        usuario=usuario,
        catalogo_investigaciones=catalogo_investigaciones,
        buscar=buscar,
        area_seleccionada=area_seleccionada,
    )

# ============================================================
# INVITAR ESTUDIANTE
# ============================================================

@app.route(
    "/grupos/<int:grupo_id>/invitar",
    methods=["POST"]
)
@roles_requeridos("estudiante")
def invitar_estudiante(grupo_id):

    usuario = usuario_actual()

    estudiante_id = request.form.get(
        "estudiante_id",
        type=int
    )


    with conectar_db() as db:

        grupo = db.execute(
            """
            SELECT *
            FROM grupos
            WHERE id = ?
            AND lider_id = ?
            """,
            (
                grupo_id,
                usuario["id"]
            )
        ).fetchone()


        if not grupo:

            flash(
                "Solo el líder puede enviar invitaciones.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        cantidad = db.execute(
            """
            SELECT COUNT(*)
            FROM miembros_grupo
            WHERE grupo_id = ?
            AND estado = 'activo'
            """,
            (grupo_id,)
        ).fetchone()[0]


        if cantidad >= 3:

            flash(
                "El grupo ya tiene el máximo de 3 estudiantes.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        if not estudiante_id:

            flash(
                "Selecciona un estudiante.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        estudiante = db.execute(
            """
            SELECT id
            FROM usuarios
            WHERE id = ?
            AND rol = 'estudiante'
            AND activo = 1
            """,
            (estudiante_id,)
        ).fetchone()


        if not estudiante:

            flash(
                "El usuario seleccionado no es un estudiante válido.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        if estudiante_id == usuario["id"]:

            flash(
                "No puedes invitarte a ti mismo.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        ya_pertenece = db.execute(
            """
            SELECT id
            FROM miembros_grupo
            WHERE estudiante_id = ?
            AND estado = 'activo'
            """,
            (estudiante_id,)
        ).fetchone()


        if ya_pertenece:

            flash(
                "Ese estudiante ya pertenece a un grupo.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        pendiente = db.execute(
            """
            SELECT id
            FROM invitaciones_grupo
            WHERE grupo_id = ?
            AND invitado_id = ?
            AND estado = 'pendiente'
            """,
            (
                grupo_id,
                estudiante_id
            )
        ).fetchone()


        if pendiente:

            flash(
                "Ya existe una invitación pendiente.",
                "aviso"
            )

            return redirect(
                url_for("grupos")
            )


        db.execute(
            """
            INSERT INTO invitaciones_grupo
            (
                grupo_id,
                invitado_id,
                invitado_por
            )
            VALUES (?, ?, ?)
            """,
            (
                grupo_id,
                estudiante_id,
                usuario["id"]
            )
        )


    flash(
        "Invitación enviada.",
        "exito"
    )

    return redirect(
        url_for("grupos")
    )


# ============================================================
# RESPONDER INVITACIÓN
# ============================================================

@app.route(
    "/invitaciones/<int:invitacion_id>/<accion>",
    methods=["POST"]
)
@roles_requeridos("estudiante")
def responder_invitacion(
    invitacion_id,
    accion
):

    usuario = usuario_actual()


    if accion not in (
        "aceptar",
        "rechazar"
    ):

        return redirect(
            url_for("grupos")
        )


    with conectar_db() as db:

        invitacion = db.execute(
            """
            SELECT *
            FROM invitaciones_grupo
            WHERE id = ?
            AND invitado_id = ?
            AND estado = 'pendiente'
            """,
            (
                invitacion_id,
                usuario["id"]
            )
        ).fetchone()


        if not invitacion:

            flash(
                "Invitación no encontrada.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        if accion == "rechazar":

            db.execute(
                """
                UPDATE invitaciones_grupo
                SET estado = 'rechazada'
                WHERE id = ?
                """,
                (invitacion_id,)
            )

            flash(
                "Invitación rechazada.",
                "aviso"
            )

            return redirect(
                url_for("grupos")
            )


        ya_grupo = db.execute(
            """
            SELECT id
            FROM miembros_grupo
            WHERE estudiante_id = ?
            AND estado = 'activo'
            """,
            (usuario["id"],)
        ).fetchone()


        if ya_grupo:

            flash(
                "Ya perteneces a un grupo.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        cantidad = db.execute(
            """
            SELECT COUNT(*)
            FROM miembros_grupo
            WHERE grupo_id = ?
            AND estado = 'activo'
            """,
            (invitacion["grupo_id"],)
        ).fetchone()[0]


        if cantidad >= 3:

            db.execute(
                """
                UPDATE invitaciones_grupo
                SET estado = 'rechazada'
                WHERE id = ?
                """,
                (invitacion_id,)
            )

            flash(
                "El grupo ya alcanzó el máximo de 3 estudiantes.",
                "error"
            )

            return redirect(
                url_for("grupos")
            )


        db.execute(
            """
            INSERT INTO miembros_grupo
            (
                grupo_id,
                estudiante_id,
                es_lider,
                estado
            )
            VALUES (?, ?, 0, 'activo')
            """,
            (
                invitacion["grupo_id"],
                usuario["id"]
            )
        )


        db.execute(
            """
            UPDATE invitaciones_grupo
            SET estado = 'aceptada'
            WHERE id = ?
            """,
            (invitacion_id,)
        )


    flash(
        "¡Te uniste al grupo!",
        "exito"
    )

    return redirect(
        url_for("grupos")
    )



@app.route("/admin/capitulo/<int:nivel>")
@login_requerido
def admin_capitulo(nivel):
    usuario = usuario_actual()

    if usuario["rol"] != "admin":
        flash("No tienes permiso para acceder a esta sección.", "error")
        return redirect(url_for("panel"))

    nombres_niveles = {
        1: "Presentación del tema",
        2: "Capítulo I",
        3: "Capítulo II",
        4: "Capítulo III",
        5: "Capítulo IV",
        6: "Capítulo V"
    }

    if nivel not in nombres_niveles:
        flash("El capítulo solicitado no existe.", "error")
        return redirect(url_for("panel"))

    with conectar_db() as db:
        investigaciones = db.execute(
            """
            SELECT
                i.id,
                i.titulo,
                i.nivel_actual,
                i.estado,
                i.finalizada,
                g.nombre AS grupo_nombre,
                t.nombre AS profesor_nombre,
                t.apellido AS profesor_apellido,
                e.estado AS estado_entrega,
                e.enviado_en,
                e.revisado_en,
                e.comentario_profesor
            FROM investigaciones i
            LEFT JOIN grupos g ON g.id = i.grupo_id
            LEFT JOIN usuarios t ON t.id = i.profesor_id
            LEFT JOIN entregas e
                ON e.investigacion_id = i.id
                AND e.nivel = ?
            ORDER BY g.nombre ASC, i.titulo ASC
            """,
            (nivel,)
        ).fetchall()

    total = len(investigaciones)

    presentadas = sum(
        1 for i in investigaciones
        if i["estado_entrega"] is not None
    )

    aprobadas = sum(
        1 for i in investigaciones
        if i["estado_entrega"] == "Aprobado"
    )

    en_revision = sum(
        1 for i in investigaciones
        if i["estado_entrega"] == "Pendiente de revisión"
    )

    correcciones = sum(
        1 for i in investigaciones
        if i["estado_entrega"] == "Necesita correcciones"
    )

    sin_entregar = total - presentadas

    porcentaje_presentadas = round(
        presentadas * 100 / total
    ) if total else 0

    porcentaje_aprobadas = round(
        aprobadas * 100 / total
    ) if total else 0

    estadisticas_capitulo = {
        "total": total,
        "presentadas": presentadas,
        "aprobadas": aprobadas,
        "revision": en_revision,
        "correcciones": correcciones,
        "sin_presentar": sin_entregar,
        "porcentaje_presentadas": porcentaje_presentadas,
        "porcentaje_aprobadas": porcentaje_aprobadas
    }

    return render_template(
        "capitulo_admin.html",
        usuario=usuario,
        nivel=nivel,
        nombre_capitulo=nombres_niveles[nivel],
        investigaciones_capitulo=investigaciones,
        estadisticas_capitulo=estadisticas_capitulo
    )




@app.route("/elegir-tema", methods=["GET"])
@login_requerido
def elegir_tema():

    usuario = usuario_actual()

    if usuario["rol"] != "estudiante":
        flash("Esta sección es exclusiva para estudiantes.", "error")
        return redirect(url_for("investigaciones"))

    grupo = obtener_grupo_usuario(usuario["id"])

    if not grupo:
        flash("Primero debes crear tu grupo.", "error")
        return redirect(url_for("grupos"))

    if not grupo["es_lider"]:
        flash("Solo el líder del grupo puede proponer el tema.", "error")
        return redirect(url_for("investigaciones"))

    investigacion = obtener_investigacion_usuario(usuario["id"])

    if investigacion:
        flash("Tu grupo ya tiene una investigación registrada.", "aviso")
        return redirect(url_for("investigaciones"))

    return render_template(
        "elegir_tema.html",
        usuario=usuario,
        grupo=grupo,
        areas=AREAS
    )



# ============================================================
# INVESTIGACIONES
# ============================================================


@app.route(
    "/investigaciones",
    methods=["GET", "POST"]
)
@login_requerido
def investigaciones():

    usuario = usuario_actual()

    # ========================================================
    # CREAR INVESTIGACIÓN — NIVEL 1
    # ========================================================

    if request.method == "POST":

        if usuario["rol"] != "estudiante":
            flash(
                "Solo los estudiantes pueden registrar el tema.",
                "error"
            )
            return redirect(url_for("investigaciones"))

        grupo = obtener_grupo_usuario(usuario["id"])

        if not grupo:
            flash(
                "Primero debes crear tu grupo.",
                "error"
            )
            return redirect(url_for("grupos"))

        # Solo el líder puede presentar la investigación.
        # Puede hacerlo aunque todavía no tenga integrantes.

        if not grupo["es_lider"]:
            flash(
                "Solo el líder puede registrar la investigación.",
                "error"
            )
            return redirect(url_for("investigaciones"))

        # ====================================================
        # COMPROBAR INTEGRANTES Y DUPLICADOS
        # ====================================================

        with conectar_db() as db:

            cantidad_miembros = db.execute(
                """
                SELECT COUNT(*)
                FROM miembros_grupo
                WHERE grupo_id = ?
                  AND estado = 'activo'
                """,
                (grupo["id"],)
            ).fetchone()[0]

            existe = db.execute(
                """
                SELECT id
                FROM investigaciones
                WHERE grupo_id = ?
                """,
                (grupo["id"],)
            ).fetchone()

        # Se permite presentar con 1, 2 o 3 integrantes.
        # Nunca se permite superar los 3 integrantes activos.

        if cantidad_miembros > 3:
            flash(
                "El grupo no puede tener más de 3 estudiantes activos.",
                "error"
            )
            return redirect(url_for("grupos"))

        if cantidad_miembros < 1:
            flash(
                "Debe existir al menos un integrante en el grupo.",
                "error"
            )
            return redirect(url_for("grupos"))

        if existe:
            flash(
                "Tu grupo ya tiene una investigación registrada.",
                "aviso"
            )
            return redirect(url_for("investigaciones"))

        # ====================================================
        # LEER DATOS DEL FORMULARIO
        # ====================================================

        titulo = request.form.get(
            "titulo", ""
        ).strip()

        descripcion = request.form.get(
            "descripcion", ""
        ).strip()

        area = request.form.get(
            "area_principal", ""
        ).strip()

        subarea = request.form.get(
            "subarea", ""
        ).strip()

        # ====================================================
        # VALIDAR CAMPOS OBLIGATORIOS
        # ====================================================

        if not titulo or not area or not subarea:
            flash(
                "Completa el título, área y subárea.",
                "error"
            )
            return redirect(url_for("investigaciones"))

        if len(titulo) > 250:
            flash(
                "El título es demasiado largo.",
                "error"
            )
            return redirect(url_for("investigaciones"))

        if area not in AREAS or subarea not in AREAS[area]:
            flash(
                "El área o la subárea seleccionada no es válida.",
                "error"
            )
            return redirect(url_for("investigaciones"))

        # ====================================================
        # CREAR INVESTIGACIÓN Y SUS SEIS NIVELES
        # ====================================================

        with conectar_db() as db:

            cursor = db.execute(
                """
                INSERT INTO investigaciones
                (
                    grupo_id,
                    titulo,
                    descripcion,
                    area_principal,
                    subarea,
                    nivel_actual,
                    estado,
                    estado_evaluacion
                )
                VALUES (?, ?, ?, ?, ?, 1, 'En proceso', 'Pendiente')
                """,
                (
                    grupo["id"],
                    titulo,
                    descripcion,
                    area,
                    subarea
                )
            )

            investigacion_id = cursor.lastrowid

            for nivel in range(1, 7):

                estado_nivel = (
                    "Pendiente"
                    if nivel == 1
                    else "Bloqueado"
                )

                db.execute(
                    """
                    INSERT INTO niveles_investigacion
                    (
                        investigacion_id,
                        nivel,
                        estado
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        investigacion_id,
                        nivel,
                        estado_nivel
                    )
                )

        flash(
            "¡Tema de investigación registrado correctamente!",
            "exito"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )

    # ========================================================
    # LISTADO DE INVESTIGACIONES — ESTUDIANTE
    # ========================================================

    if usuario["rol"] == "estudiante":

        investigacion = obtener_investigacion_usuario(
            usuario["id"]
        )

        return render_template(
            "proyectos.html",
            investigaciones=(
                [investigacion] if investigacion else []
            ),
            usuario=usuario,
            areas=AREAS
        )

    # ========================================================
    # LISTADO DE INVESTIGACIONES — PROFESOR
    # ========================================================

    if usuario["rol"] == "tutor":

        with conectar_db() as db:

            lista = db.execute(
                """
                SELECT
                    i.*,
                    g.nombre AS grupo_nombre
                FROM investigaciones i
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                ORDER BY i.creado_en DESC
                """,
                (usuario["id"],)
            ).fetchall()

        return render_template(
            "proyectos.html",
            investigaciones=lista,
            usuario=usuario,
            areas=AREAS
        )

    # ========================================================
    # LISTADO DE INVESTIGACIONES — ADMINISTRADOR
    # ========================================================

    with conectar_db() as db:

        lista = db.execute(
            """
            SELECT
                i.*,
                g.nombre AS grupo_nombre,
                u.nombre AS profesor_nombre,
                u.apellido AS profesor_apellido
            FROM investigaciones i
            JOIN grupos g
                ON g.id = i.grupo_id
            LEFT JOIN usuarios u
                ON u.id = i.profesor_id
            ORDER BY i.creado_en DESC
            """
        ).fetchall()

    return render_template(
        "proyectos.html",
        investigaciones=lista,
        usuario=usuario,
        areas=AREAS
    )




# ============================================================
# TEMAS DISPONIBLES PARA PROFESORES
# ============================================================

@app.route("/temas")
@roles_requeridos("admin", "tutor")
def temas():

    usuario = usuario_actual()

    area = request.args.get(
        "area",
        ""
    ).strip()

    subarea = request.args.get(
        "subarea",
        ""
    ).strip()


    with conectar_db() as db:

        consulta = """
            SELECT
                i.*,
                g.nombre AS grupo_nombre
            FROM investigaciones i
            JOIN grupos g
                ON g.id = i.grupo_id
            WHERE i.profesor_id IS NULL
        """

        parametros = []


        if area:

            consulta += """
                AND i.area_principal = ?
            """

            parametros.append(area)


        if subarea:

            consulta += """
                AND i.subarea = ?
            """

            parametros.append(subarea)


        consulta += """
            ORDER BY i.creado_en DESC
        """


        lista = db.execute(
            consulta,
            parametros
        ).fetchall()


    return render_template(
        "temas.html",
        investigaciones=lista,
        area_seleccionada=area,
        subarea_seleccionada=subarea,
        usuario=usuario
    )


# ============================================================
# PROFESOR ELIGE INVESTIGACIÓN
# IMPORTANTE:
# SOLO EL PROFESOR ASUME EL TEMA.
# EL ADMINISTRADOR SUPERVISA, PERO NO SE ASIGNA COMO PROFESOR.
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/elegir",
    methods=["POST"]
)
@roles_requeridos("tutor")
def elegir_investigacion(
    investigacion_id
):

    usuario = usuario_actual()


    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()


        if not investigacion:

            flash(
                "Investigación no encontrada.",
                "error"
            )

            return redirect(
                url_for("temas")
            )


        if investigacion["profesor_id"]:

            if investigacion["profesor_id"] == usuario["id"]:

                flash(
                    "Esta investigación ya está asignada a ti.",
                    "aviso"
                )

            else:

                flash(
                    "Esta investigación ya tiene profesor asignado.",
                    "error"
                )

            return redirect(
                url_for("temas")
            )


        db.execute(
            """
            UPDATE investigaciones
            SET
                profesor_id = ?,
                estado = 'En proceso',
                estado_evaluacion = 'En proceso'
            WHERE id = ?
            AND profesor_id IS NULL
            """,
            (
                usuario["id"],
                investigacion_id
            )
        )


    flash(
        "Investigación seleccionada correctamente.",
        "exito"
    )

    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
    )


# ============================================================
# ASIGNACIÓN MUTUA ENTRE ADMINISTRADOR Y TUTOR
# ============================================================

@app.route(
    "/admin/investigaciones/<int:investigacion_id>/proponer-tutor",
    methods=["POST"]
)
@roles_requeridos("admin")
def proponer_tutor(investigacion_id):

    usuario = usuario_actual()
    tutor_id = request.form.get("tutor_id", type=int)

    if not tutor_id:
        flash("Selecciona un tutor.", "error")
        return redirect(url_for("panel"))

    with conectar_db() as db:

        investigacion = db.execute("""
            SELECT id, profesor_id, finalizada
            FROM investigaciones
            WHERE id = ?
        """, (investigacion_id,)).fetchone()

        tutor = db.execute("""
            SELECT id
            FROM usuarios
            WHERE id = ?
              AND rol = 'tutor'
              AND activo = 1
        """, (tutor_id,)).fetchone()

        if not investigacion:
            flash("La investigación no existe.", "error")
            return redirect(url_for("panel"))

        if investigacion["profesor_id"] is not None:
            flash("La investigación ya tiene un tutor asignado.", "error")
            return redirect(url_for("panel"))

        if investigacion["finalizada"]:
            flash("No puedes asignar una investigación finalizada.", "error")
            return redirect(url_for("panel"))

        if not tutor:
            flash("El tutor seleccionado no es válido.", "error")
            return redirect(url_for("panel"))

        pendiente = db.execute("""
            SELECT id
            FROM solicitudes_asignacion
            WHERE investigacion_id = ?
              AND estado = 'Pendiente'
            LIMIT 1
        """, (investigacion_id,)).fetchone()

        if pendiente:
            flash(
                "Esta investigación ya tiene una propuesta pendiente.",
                "aviso"
            )
            return redirect(url_for("panel"))

        db.execute("""
            INSERT INTO solicitudes_asignacion (
                investigacion_id,
                tutor_id,
                propuesto_por,
                tipo
            )
            VALUES (?, ?, ?, 'admin_a_tutor')
        """, (investigacion_id, tutor_id, usuario["id"]))

    flash("Propuesta enviada al tutor.", "exito")
    return redirect(url_for("panel"))


@app.route(
    "/asignaciones/<int:solicitud_id>/responder",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def responder_asignacion(solicitud_id):

    usuario = usuario_actual()
    respuesta = request.form.get("respuesta", "").strip()

    if respuesta not in ("Aceptar", "Rechazar"):
        flash("Respuesta no válida.", "error")
        return redirect(url_for("panel"))

    with conectar_db() as db:

        solicitud = db.execute("""
            SELECT
                s.*,
                i.profesor_id,
                i.finalizada
            FROM solicitudes_asignacion AS s
            JOIN investigaciones AS i
                ON i.id = s.investigacion_id
            WHERE s.id = ?
              AND s.estado = 'Pendiente'
        """, (solicitud_id,)).fetchone()

        if not solicitud:
            flash("La solicitud ya no está pendiente.", "aviso")
            return redirect(url_for("panel"))

        if solicitud["tipo"] == "admin_a_tutor":
            autorizado = (
                usuario["rol"] == "tutor"
                and usuario["id"] == solicitud["tutor_id"]
            )
        else:
            autorizado = usuario["rol"] == "admin"

        if not autorizado:
            flash("No tienes permiso para responder.", "error")
            return redirect(url_for("panel"))

        if respuesta == "Aceptar":

            if (
                solicitud["profesor_id"] is not None
                or solicitud["finalizada"]
            ):
                db.execute("""
                    UPDATE solicitudes_asignacion
                    SET estado = 'Rechazada',
                        respuesta_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (solicitud_id,))

                flash(
                    "La investigación ya no está disponible.",
                    "error"
                )
                return redirect(url_for("panel"))

            pendientes = db.execute("""
                SELECT id
                FROM solicitudes_asignacion
                WHERE investigacion_id = ?
                  AND estado = 'Pendiente'
                  AND id != ?
                LIMIT 1
            """, (
                solicitud["investigacion_id"],
                solicitud_id
            )).fetchone()

            if pendientes:
                flash(
                    "Hay otra propuesta pendiente para esta investigación. "
                    "Resuélvela antes de aceptar.",
                    "aviso"
                )
                return redirect(url_for("panel"))

            cursor = db.execute("""
                UPDATE investigaciones
                SET profesor_id = ?,
                    estado = 'En proceso',
                    estado_evaluacion = 'En proceso'
                WHERE id = ?
                  AND profesor_id IS NULL
                  AND finalizada = 0
            """, (
                solicitud["tutor_id"],
                solicitud["investigacion_id"]
            ))

            if cursor.rowcount != 1:
                flash(
                    "No se pudo confirmar la asignación.",
                    "error"
                )
                return redirect(url_for("panel"))

            db.execute("""
                UPDATE solicitudes_asignacion
                SET estado = 'Aceptada',
                    respuesta_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (solicitud_id,))

            db.execute("""
                UPDATE solicitudes_asignacion
                SET estado = 'Rechazada',
                    respuesta_en = CURRENT_TIMESTAMP
                WHERE investigacion_id = ?
                  AND id != ?
                  AND estado = 'Pendiente'
            """, (
                solicitud["investigacion_id"],
                solicitud_id
            ))

        else:
            db.execute("""
                UPDATE solicitudes_asignacion
                SET estado = 'Rechazada',
                    respuesta_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (solicitud_id,))

    if respuesta == "Aceptar":
        flash("Asignación confirmada correctamente.", "exito")
    else:
        flash("Propuesta rechazada.", "aviso")

    return redirect(url_for("panel"))


@app.route(
    "/tutor/investigaciones/<int:investigacion_id>/solicitar",
    methods=["POST"]
)
@roles_requeridos("tutor")
def solicitar_investigacion(investigacion_id):

    usuario = usuario_actual()

    with conectar_db() as db:

        investigacion = db.execute("""
            SELECT id, profesor_id, finalizada
            FROM investigaciones
            WHERE id = ?
        """, (investigacion_id,)).fetchone()

        if not investigacion:
            flash("La investigación no existe.", "error")
            return redirect(url_for("panel"))

        if (
            investigacion["profesor_id"] is not None
            or investigacion["finalizada"]
        ):
            flash("Esta investigación no está disponible.", "error")
            return redirect(url_for("panel"))

        pendiente = db.execute("""
            SELECT id
            FROM solicitudes_asignacion
            WHERE investigacion_id = ?
              AND estado = 'Pendiente'
            LIMIT 1
        """, (investigacion_id,)).fetchone()

        if pendiente:
            flash(
                "Esta investigación ya tiene una solicitud pendiente.",
                "aviso"
            )
            return redirect(url_for("panel"))

        db.execute("""
            INSERT INTO solicitudes_asignacion (
                investigacion_id,
                tutor_id,
                propuesto_por,
                tipo
            )
            VALUES (?, ?, ?, 'tutor_a_admin')
        """, (
            investigacion_id,
            usuario["id"],
            usuario["id"]
        ))

    flash("Solicitud enviada al administrador.", "exito")
    return redirect(url_for("panel"))



# ============================================================
# DETALLE DE INVESTIGACIÓN
# ============================================================

@app.route("/investigaciones/<int:investigacion_id>")
@login_requerido
def detalle_investigacion(investigacion_id):

    usuario = usuario_actual()

    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT
                i.*,
                g.nombre AS grupo_nombre,
                t.nombre AS profesor_nombre,
                t.apellido AS profesor_apellido
            FROM investigaciones i
            JOIN grupos g ON g.id = i.grupo_id
            LEFT JOIN usuarios t ON t.id = i.profesor_id
            WHERE i.id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            flash("Investigación no encontrada.", "error")
            return redirect(url_for("panel"))

        permitido = False

        if usuario["rol"] == "admin":
            permitido = True

        elif usuario["rol"] == "tutor":
            permitido = (
                investigacion["profesor_id"] == usuario["id"]
            )

        else:
            permitido = es_miembro_investigacion(
                usuario["id"],
                investigacion_id
            )

        if not permitido:
            flash("No tienes permiso para acceder.", "error")
            return redirect(url_for("panel"))

        miembros = db.execute(
            """
            SELECT
                u.id,
                u.nombre,
                u.apellido,
                u.usuario,
                mg.es_lider
            FROM miembros_grupo mg
            JOIN usuarios u ON u.id = mg.estudiante_id
            WHERE mg.grupo_id = ?
              AND mg.estado = 'activo'
            ORDER BY mg.es_lider DESC, u.apellido
            """,
            (investigacion["grupo_id"],)
        ).fetchall()

        niveles = db.execute(
            """
            SELECT *
            FROM niveles_investigacion
            WHERE investigacion_id = ?
            ORDER BY nivel
            """,
            (investigacion_id,)
        ).fetchall()

        if usuario["rol"] == "estudiante":
            niveles = ocultar_notas_estudiante(niveles)

        entregas = db.execute(
            """
            SELECT *
            FROM entregas
            WHERE investigacion_id = ?
            ORDER BY nivel
            """,
            (investigacion_id,)
        ).fetchall()

              # El estudiante no recibe la columna nota del historial.
        if usuario["rol"] == "estudiante":
            historial_entregas = db.execute(
                """
                SELECT
                    id,
                    entrega_id,
                    investigacion_id,
                    nivel,
                    version,
                    titulo,
                    archivo,
                    texto,
                    nota_estudiante,
                    estado,
                    observaciones,
                    enviado_por,
                    enviado_en,
                    revisado_en
                FROM historial_entregas
                WHERE investigacion_id = ?
                ORDER BY nivel, version DESC
                """,
                (investigacion_id,)
            ).fetchall()

        else:
            historial_entregas = db.execute(
                """
                SELECT *
                FROM historial_entregas
                WHERE investigacion_id = ?
                ORDER BY nivel, version DESC
                """,
                (investigacion_id,)
            ).fetchall()

        tareas = db.execute(
            """
            SELECT *
            FROM tareas
            WHERE investigacion_id = ?
            ORDER BY fecha_limite, id
            """,
            (investigacion_id,)
        ).fetchall()

        fuentes = db.execute(
            """
            SELECT *
            FROM fuentes
            WHERE investigacion_id = ?
            ORDER BY autor, anio
            """,
            (investigacion_id,)
        ).fetchall()

        comentarios = db.execute(
            """
            SELECT
                c.*,
                u.nombre,
                u.apellido,
                u.rol
            FROM comentarios c
            JOIN usuarios u ON u.id = c.autor_id
            WHERE c.investigacion_id = ?
            ORDER BY c.creado_en
            """,
            (investigacion_id,)
        ).fetchall()

        reuniones = db.execute(
            """
            SELECT
                sr.*,
                u.nombre AS estudiante_nombre,
                u.apellido AS estudiante_apellido
            FROM solicitudes_reunion sr
            JOIN usuarios u ON u.id = sr.estudiante_id
            WHERE sr.investigacion_id = ?
            ORDER BY sr.fecha_solicitada, sr.hora_solicitada
            """,
            (investigacion_id,)
        ).fetchall()

        rubricas = []

        if usuario["rol"] in ("admin", "tutor"):
            rubricas = db.execute(
                """
                SELECT
                    r.*,
                    u.nombre AS evaluador_nombre,
                    u.apellido AS evaluador_apellido
                FROM rubricas r
                JOIN usuarios u ON u.id = r.evaluador_id
                WHERE r.investigacion_id = ?
                ORDER BY r.nivel, r.evaluado_en DESC
                """,
                (investigacion_id,)
            ).fetchall()

    return render_template(
        "detalle_proyecto.html",
        investigacion=investigacion,
        proyecto=investigacion,
        miembros=miembros,
        niveles=niveles,
        entregas=entregas,
        historial_entregas=historial_entregas,
        tareas=tareas,
        fuentes=fuentes,
        comentarios=comentarios,
        reuniones=reuniones,
        rubricas=rubricas,
        usuario=usuario
    )

# ============================================================
# MIS ENTREGAS
# ============================================================

@app.route("/mis-entregas")
@login_requerido
def mis_entregas():

    usuario = usuario_actual()

    # El estudiante abre su propia investigación.
    if usuario["rol"] == "estudiante":

        investigacion = obtener_investigacion_usuario(
            usuario["id"]
        )

        if not investigacion:
            flash(
                "Todavía no tienes una investigación asignada.",
                "aviso"
            )
            return redirect(url_for("investigaciones"))

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion["id"]
            )
        )

    # El tutor y administrador acceden a sus investigaciones.
    return redirect(url_for("investigaciones"))


# ============================================================
# APERTURA SEGURA DE ARCHIVOS DE INVESTIGACIÓN
# ============================================================

def usuario_puede_ver_investigacion(usuario, investigacion_id):

    if usuario is None:
        return False

    with conectar_db() as db:
        investigacion = db.execute(
            """
            SELECT profesor_id
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

    if investigacion is None:
        return False

    if usuario["rol"] == "admin":
        return True

    if usuario["rol"] == "tutor":
        return investigacion["profesor_id"] == usuario["id"]

    if usuario["rol"] == "estudiante":
        return es_miembro_investigacion(
            usuario["id"],
            investigacion_id
        )

    return False


@app.route("/historial-entregas/<int:historial_id>/archivo")
@login_requerido
def abrir_archivo_historial(historial_id):

    usuario = usuario_actual()

    with conectar_db() as db:
        version = db.execute(
            """
            SELECT archivo, investigacion_id
            FROM historial_entregas
            WHERE id = ?
            """,
            (historial_id,)
        ).fetchone()

    if version is None:
        flash("No se encontró esa versión.", "error")
        return redirect(url_for("panel"))

    if not usuario_puede_ver_investigacion(
        usuario,
        version["investigacion_id"]
    ):
        flash("No tienes permiso para abrir este archivo.", "error")
        return redirect(url_for("panel"))

    nombre_archivo = version["archivo"]

    if not nombre_archivo:
        flash("Esta versión no tiene un archivo adjunto.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=version["investigacion_id"]
        ))

    return send_from_directory(
        str(UPLOAD_DIR),
        nombre_archivo,
        as_attachment=False
    )


@app.route("/entregas/<int:entrega_id>/archivo")
@login_requerido
def abrir_archivo_entrega_actual(entrega_id):

    usuario = usuario_actual()

    with conectar_db() as db:
        entrega = db.execute(
            """
            SELECT archivo, investigacion_id
            FROM entregas
            WHERE id = ?
            """,
            (entrega_id,)
        ).fetchone()

    if entrega is None:
        flash("No se encontró la entrega.", "error")
        return redirect(url_for("panel"))

    if not usuario_puede_ver_investigacion(
        usuario,
        entrega["investigacion_id"]
    ):
        flash("No tienes permiso para abrir este archivo.", "error")
        return redirect(url_for("panel"))

    nombre_archivo = entrega["archivo"]

    if not nombre_archivo:
        flash("Esta entrega no tiene un archivo adjunto.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=entrega["investigacion_id"]
        ))

    return send_from_directory(
        str(UPLOAD_DIR),
        nombre_archivo,
        as_attachment=False
    )






# ============================================================
# ENTREGAR NIVEL — HISTORIAL DE VERSIONES Y NOTIFICACIONES
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/entregar",
    methods=["POST"]
)
@roles_requeridos("estudiante")
def entregar_nivel(investigacion_id):

    usuario = usuario_actual()

    # 1. Verificar pertenencia a la investigación
    if not es_miembro_investigacion(
        usuario["id"],
        investigacion_id
    ):
        flash("No tienes permiso.", "error")
        return redirect(url_for("panel"))

    titulo = request.form.get("titulo", "").strip()
    nivel = request.form.get("nivel", type=int)
    texto = request.form.get("texto", "").strip()
    nota_estudiante = request.form.get(
        "nota_estudiante", ""
    ).strip()

    archivo = request.files.get("archivo")

    if not titulo:
        flash("Escribe el título de la entrega.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    if nivel is None or not 1 <= nivel <= 6:
        flash("Nivel no válido.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    tiene_archivo = bool(archivo and archivo.filename)

    if not texto and not tiene_archivo:
        flash(
            "Escribe el contenido o adjunta un archivo.",
            "error"
        )
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    # 2. Validar archivo
    nombre_original = None

    if tiene_archivo:
        nombre_original = secure_filename(archivo.filename)

        if not nombre_original:
            flash("El nombre del archivo no es válido.", "error")
            return redirect(url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            ))

        if not archivo_permitido(nombre_original):
            flash("Tipo de archivo no permitido.", "error")
            return redirect(url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            ))

    archivo_guardado = None
    version = None

    try:
        with conectar_db() as db:

            # 3. Obtener investigación
            investigacion = db.execute(
                """
                SELECT *
                FROM investigaciones
                WHERE id = ?
                """,
                (investigacion_id,)
            ).fetchone()

            if not investigacion:
                flash("Investigación no encontrada.", "error")
                return redirect(url_for("panel"))

            if investigacion["finalizada"]:
                flash(
                    "La investigación ya fue finalizada.",
                    "error"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # 4. Verificar nivel
            nivel_db = db.execute(
                """
                SELECT *
                FROM niveles_investigacion
                WHERE investigacion_id = ?
                  AND nivel = ?
                """,
                (investigacion_id, nivel)
            ).fetchone()

            if not nivel_db:
                flash("Nivel no encontrado.", "error")
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            if nivel != investigacion["nivel_actual"]:
                flash(
                    "Solo puedes trabajar en el nivel habilitado.",
                    "error"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            estado_nivel = nivel_db["estado"]

            if estado_nivel in (
                "Bloqueado",
                "Aprobado",
                "Pendiente de revisión"
            ):
                flash(
                    "No puedes enviar este nivel en su estado actual.",
                    "error"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # 5. Guardar archivo
            if tiene_archivo:
                nombre_archivo = (
                    f"{investigacion_id}_nivel{nivel}_"
                    f"{uuid.uuid4().hex}_{nombre_original}"
                )

                ruta_archivo = UPLOAD_DIR / nombre_archivo
                archivo.save(ruta_archivo)
                archivo_guardado = ruta_archivo
            else:
                nombre_archivo = None

            # 6. Calcular versión
            resultado = db.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                    AS siguiente_version
                FROM historial_entregas
                WHERE investigacion_id = ?
                  AND nivel = ?
                """,
                (investigacion_id, nivel)
            ).fetchone()

            version = resultado["siguiente_version"]

            # 7. Guardar entrega actual
            db.execute(
                """
                INSERT INTO entregas (
                    investigacion_id,
                    nivel,
                    titulo,
                    archivo,
                    texto,
                    nota_estudiante,
                    estado
                )
                VALUES (?, ?, ?, ?, ?, ?,
                        'Pendiente de revisión')

                ON CONFLICT(investigacion_id, nivel)
                DO UPDATE SET
                    titulo = excluded.titulo,
                    archivo = excluded.archivo,
                    texto = excluded.texto,
                    nota_estudiante = excluded.nota_estudiante,
                    estado = 'Pendiente de revisión',
                    comentario_profesor = NULL,
                    enviado_en = CURRENT_TIMESTAMP,
                    revisado_en = NULL
                """,
                (
                    investigacion_id,
                    nivel,
                    titulo,
                    nombre_archivo,
                    texto,
                    nota_estudiante
                )
            )

            entrega_actual = db.execute(
                """
                SELECT id
                FROM entregas
                WHERE investigacion_id = ?
                  AND nivel = ?
                """,
                (investigacion_id, nivel)
            ).fetchone()

            # 8. Guardar historial de versiones
            db.execute(
                """
                INSERT INTO historial_entregas (
                    entrega_id,
                    investigacion_id,
                    nivel,
                    version,
                    titulo,
                    archivo,
                    texto,
                    nota_estudiante,
                    estado,
                    enviado_por
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                        'Pendiente de revisión', ?)
                """,
                (
                    entrega_actual["id"],
                    investigacion_id,
                    nivel,
                    version,
                    titulo,
                    nombre_archivo,
                    texto,
                    nota_estudiante,
                    usuario["id"]
                )
            )

            # 9. Actualizar estado del nivel
            db.execute(
                """
                UPDATE niveles_investigacion
                SET
                    estado = 'Pendiente de revisión',
                    observaciones = NULL,
                    enviado_en = CURRENT_TIMESTAMP,
                    evaluado = 0
                WHERE investigacion_id = ?
                  AND nivel = ?
                """,
                (investigacion_id, nivel)
            )

            db.execute(
                """
                UPDATE investigaciones
                SET estado = 'En revisión'
                WHERE id = ?
                """,
                (investigacion_id,)
            )

            # 10. Registrar progreso
            registrar_evento_progreso_db(
                db,
                investigacion_id,
                nivel,
                f"Entrega presentada — versión {version}"
            )

            # 11. Notificaciones
            tutor_id = investigacion["profesor_id"]

            enlace_entrega = url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )

            mensaje_entrega = (
                f"El estudiante {usuario['nombre']} presentó "
                f"«{titulo}», Nivel {nivel}, versión {version}, "
                f"de la investigación "
                f"«{investigacion['titulo']}»."
            )

            destinatarios = []

            if tutor_id:
                destinatarios.append({
                    "id": tutor_id,
                    "titulo": "Nueva entrega recibida",
                    "mensaje": mensaje_entrega
                })

            else:
                administradores = db.execute(
                    """
                    SELECT id
                    FROM usuarios
                    WHERE rol = 'admin'
                      AND activo = 1
                    """
                ).fetchall()

                for administrador in administradores:
                    destinatarios.append({
                        "id": administrador["id"],
                        "titulo": "Nueva entrega sin tutor asignado",
                        "mensaje": (
                            f"{mensaje_entrega} "
                            "La investigación todavía no tiene "
                            "un tutor asignado."
                        )
                    })

            for destinatario in destinatarios:
                creada = crear_notificacion(
                    db=db,
                    usuario_id=destinatario["id"],
                    titulo=destinatario["titulo"],
                    mensaje=destinatario["mensaje"],
                    investigacion_id=investigacion_id,
                    enlace=enlace_entrega
                )

                if not creada:
                    raise RuntimeError(
                        "No se pudo guardar la notificación "
                        f"para el usuario {destinatario['id']}."
                    )

    except Exception:
        if archivo_guardado and archivo_guardado.exists():
            try:
                archivo_guardado.unlink()
            except OSError:
                app.logger.exception(
                    "No se pudo eliminar el archivo temporal."
                )

        app.logger.exception(
            "Error al guardar la entrega de la investigación %s",
            investigacion_id
        )

        flash(
            "No se pudo guardar la entrega. "
            "Comprueba el archivo e inténtalo nuevamente.",
            "error"
        )

        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    flash(
        f"¡Entrega enviada correctamente! Versión {version}.",
        "exito"
    )

    return redirect(url_for(
        "detalle_investigacion",
        investigacion_id=investigacion_id
    ))


# ============================================================
# CORRECCIONES DEL ESTUDIANTE
# CONSULTAR OBSERVACIONES Y GUARDAR PROGRESO
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/correcciones",
    methods=["GET", "POST"]
)
@roles_requeridos("estudiante")
def correcciones_estudiante(investigacion_id):

    usuario = usuario_actual()

    # --------------------------------------------------------
    # VERIFICAR PERTENENCIA
    # --------------------------------------------------------

    if not es_miembro_investigacion(
        usuario["id"],
        investigacion_id
    ):
        flash("No tienes permiso para acceder.", "error")
        return redirect(url_for("panel"))

    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT
                id,
                titulo,
                nivel_actual,
                finalizada
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            flash("Investigación no encontrada.", "error")
            return redirect(url_for("panel"))

        # ----------------------------------------------------
        # GUARDAR CHECKBOXES
        # ----------------------------------------------------

        if request.method == "POST":

            historial_id = request.form.get(
                "historial_id",
                type=int
            )

            if not historial_id:
                flash("No se identificó la revisión.", "error")
                return redirect(
                    url_for(
                        "correcciones_estudiante",
                        investigacion_id=investigacion_id
                    )
                )

            historial_actual = db.execute(
                """
                SELECT h.id
                FROM historial_entregas h
                WHERE h.id = ?
                  AND h.investigacion_id = ?
                  AND h.estado = 'Necesita correcciones'
                  AND h.version = (
                      SELECT MAX(h2.version)
                      FROM historial_entregas h2
                      WHERE h2.investigacion_id = h.investigacion_id
                        AND h2.nivel = h.nivel
                  )
                """,
                (historial_id, investigacion_id)
            ).fetchone()

            if not historial_actual:
                flash(
                    "Esta revisión ya no está disponible para modificar.",
                    "error"
                )
                return redirect(
                    url_for(
                        "correcciones_estudiante",
                        investigacion_id=investigacion_id
                    )
                )

            # Obtener únicamente los IDs enviados
            ids_marcados = set()

            for valor in request.form.getlist("observaciones"):
                try:
                    ids_marcados.add(int(valor))
                except (ValueError, TypeError):
                    continue

            # Desmarcar todas las observaciones de esta versión
            db.execute(
                """
                UPDATE observaciones_correccion
                SET
                    corregida = 0,
                    corregida_en = NULL
                WHERE historial_entrega_id = ?
                """,
                (historial_id,)
            )

            # Marcar las seleccionadas
            for observacion_id in ids_marcados:

                db.execute(
                    """
                    UPDATE observaciones_correccion
                    SET
                        corregida = 1,
                        corregida_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                      AND historial_entrega_id = ?
                    """,
                    (
                        observacion_id,
                        historial_id
                    )
                )

            flash(
                "Tu progreso de correcciones se guardó correctamente.",
                "exito"
            )

            return redirect(
                url_for(
                    "correcciones_estudiante",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # CONSULTAR VERSIONES QUE TIENEN OBSERVACIONES
        # ----------------------------------------------------

        registros = db.execute(
            """
            SELECT
                h.*,
                CASE
                    WHEN h.version = (
                        SELECT MAX(h2.version)
                        FROM historial_entregas h2
                        WHERE h2.investigacion_id = h.investigacion_id
                          AND h2.nivel = h.nivel
                    )
                    THEN 1
                    ELSE 0
                END AS es_ultima
            FROM historial_entregas h
            WHERE h.investigacion_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM observaciones_correccion oc
                  WHERE oc.historial_entrega_id = h.id
              )
            ORDER BY h.nivel ASC, h.version DESC
            """,
            (investigacion_id,)
        ).fetchall()

        correcciones_pendientes = []
        correcciones_anteriores = []

        # ----------------------------------------------------
        # SEPARAR CORRECCIONES ACTUALES Y ANTERIORES
        # ----------------------------------------------------

        for registro in registros:

            observaciones = db.execute(
                """
                SELECT *
                FROM observaciones_correccion
                WHERE historial_entrega_id = ?
                ORDER BY id ASC
                """,
                (registro["id"],)
            ).fetchall()

            elemento = {
                "historial": dict(registro),
                "observaciones": [
                    dict(observacion)
                    for observacion in observaciones
                ]
            }

            if (
                registro["es_ultima"]
                and registro["estado"] == "Necesita correcciones"
            ):
                correcciones_pendientes.append(elemento)

            else:
                correcciones_anteriores.append(elemento)

    # --------------------------------------------------------
    # MOSTRAR PANTALLA
    # --------------------------------------------------------

    return render_template(
        "correcciones_estudiante.html",
        investigacion=investigacion,
        correcciones_pendientes=correcciones_pendientes,
        correcciones_anteriores=correcciones_anteriores
    )



# ============================================================
# COMPARADOR DE VERSIONES — GENERAR DIFERENCIAS
# ============================================================

def generar_comparacion_textos(texto_anterior, texto_actual):

    texto_anterior = texto_anterior or ""
    texto_actual = texto_actual or ""

    palabras_anterior = re.findall(
        r"\w+|[^\w\s]+|\s+",
        texto_anterior,
        flags=re.UNICODE
    )

    palabras_actual = re.findall(
        r"\w+|[^\w\s]+|\s+",
        texto_actual,
        flags=re.UNICODE
    )

    comparador = difflib.SequenceMatcher(
        None,
        palabras_anterior,
        palabras_actual,
        autojunk=False
    )

    anterior = []
    actual = []

    agregadas = 0
    eliminadas = 0

    for operacion, inicio_a, fin_a, inicio_b, fin_b in comparador.get_opcodes():

        fragmento_anterior = palabras_anterior[inicio_a:fin_a]
        fragmento_actual = palabras_actual[inicio_b:fin_b]

        if operacion == "equal":

            anterior.append({
                "tipo": "igual",
                "texto": "".join(fragmento_anterior)
            })

            actual.append({
                "tipo": "igual",
                "texto": "".join(fragmento_actual)
            })

        elif operacion == "delete":

            anterior.append({
                "tipo": "eliminado",
                "texto": "".join(fragmento_anterior)
            })

            eliminadas += len(re.findall(
                r"\w+",
                "".join(fragmento_anterior),
                flags=re.UNICODE
            ))

        elif operacion == "insert":

            actual.append({
                "tipo": "agregado",
                "texto": "".join(fragmento_actual)
            })

            agregadas += len(re.findall(
                r"\w+",
                "".join(fragmento_actual),
                flags=re.UNICODE
            ))

        elif operacion == "replace":

            anterior.append({
                "tipo": "eliminado",
                "texto": "".join(fragmento_anterior)
            })

            actual.append({
                "tipo": "agregado",
                "texto": "".join(fragmento_actual)
            })

            eliminadas += len(re.findall(
                r"\w+",
                "".join(fragmento_anterior),
                flags=re.UNICODE
            ))

            agregadas += len(re.findall(
                r"\w+",
                "".join(fragmento_actual),
                flags=re.UNICODE
            ))

    return {
        "anterior": anterior,
        "actual": actual,
        "agregadas": agregadas,
        "eliminadas": eliminadas
    }


# ============================================================
# COMPARADOR DE CORRECCIONES — CONSULTAR VERSIONES
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/comparador/<int:historial_id>",
    methods=["GET"]
)
@roles_requeridos("admin", "tutor")
def comparador_correcciones(investigacion_id, historial_id):

    usuario = usuario_actual()

    with conectar_db() as db:

        # ----------------------------------------------------
        # OBTENER INVESTIGACIÓN
        # ----------------------------------------------------

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            flash("Investigación no encontrada.", "error")
            return redirect(url_for("panel"))

        # ----------------------------------------------------
        # VALIDAR ASIGNACIÓN DEL TUTOR
        # ----------------------------------------------------

        if (
            usuario["rol"] == "tutor"
            and investigacion["profesor_id"] != usuario["id"]
        ):
            flash(
                "No tienes permiso para acceder a este comparador.",
                "error"
            )
            return redirect(url_for("panel"))

        # ----------------------------------------------------
        # OBTENER VERSIÓN ACTUAL
        # ----------------------------------------------------

        version_actual = db.execute(
            """
            SELECT *
            FROM historial_entregas
            WHERE id = ?
              AND investigacion_id = ?
            """,
            (historial_id, investigacion_id)
        ).fetchone()

        if not version_actual:
            flash("La versión solicitada no existe.", "error")
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # VERIFICAR QUE SEA LA ÚLTIMA VERSIÓN
        # ----------------------------------------------------

        ultima_version = db.execute(
            """
            SELECT MAX(version) AS version
            FROM historial_entregas
            WHERE entrega_id = ?
            """,
            (version_actual["entrega_id"],)
        ).fetchone()

        if ultima_version["version"] != version_actual["version"]:
            flash(
                "Solo puedes comparar la última versión presentada.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        if version_actual["estado"] != "Pendiente de revisión":
            flash(
                "Esta entrega no está pendiente de revisión.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # BUSCAR VERSIÓN ANTERIOR
        # ----------------------------------------------------

        version_anterior = db.execute(
            """
            SELECT *
            FROM historial_entregas
            WHERE entrega_id = ?
              AND nivel = ?
              AND version < ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (
                version_actual["entrega_id"],
                version_actual["nivel"],
                version_actual["version"]
            )
        ).fetchone()

        if not version_anterior:
            flash(
                "Esta entrega no tiene una versión anterior para comparar.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # OBTENER OBSERVACIONES DE LA VERSIÓN ANTERIOR
        # ----------------------------------------------------

        observaciones = db.execute(
            """
            SELECT *
            FROM observaciones_correccion
            WHERE historial_entrega_id = ?
            ORDER BY id ASC
            """,
            (version_anterior["id"],)
        ).fetchall()

        if not observaciones:
            flash(
                "La versión anterior no tiene observaciones registradas.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # COMPARAR TEXTOS
        # ----------------------------------------------------

        comparacion = generar_comparacion_textos(
            version_anterior["texto"],
            version_actual["texto"]
        )

        atendidas = sum(
            1 for observacion in observaciones
            if observacion["estado_revision"] == "Atendida"
        )

        pendientes = len(observaciones) - atendidas

    return render_template(
        "comparador_correcciones.html",
        investigacion=investigacion,
        version_anterior=version_anterior,
        version_actual=version_actual,
        observaciones=observaciones,
        comparacion=comparacion,
        atendidas=atendidas,
        pendientes=pendientes
    )


# ============================================================
# COMPARADOR DE CORRECCIONES — REGISTRAR REVISIÓN DEL TUTOR
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/comparador/<int:historial_id>/registrar",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def registrar_revision_correcciones(
    investigacion_id,
    historial_id
):

    usuario = usuario_actual()

    with conectar_db() as db:

        # ----------------------------------------------------
        # VERIFICAR INVESTIGACIÓN
        # ----------------------------------------------------

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            flash("Investigación no encontrada.", "error")
            return redirect(url_for("panel"))

        if (
            usuario["rol"] == "tutor"
            and investigacion["profesor_id"] != usuario["id"]
        ):
            flash("No tienes permiso para registrar esta revisión.", "error")
            return redirect(url_for("panel"))

        # ----------------------------------------------------
        # VERIFICAR VERSIÓN ACTUAL
        # ----------------------------------------------------

        version_actual = db.execute(
            """
            SELECT *
            FROM historial_entregas
            WHERE id = ?
              AND investigacion_id = ?
              AND estado = 'Pendiente de revisión'
            """,
            (historial_id, investigacion_id)
        ).fetchone()

        if not version_actual:
            flash(
                "La entrega ya no está disponible para revisión.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

                # ----------------------------------------------------
        # VERIFICAR QUE SEA LA ÚLTIMA VERSIÓN
        # ----------------------------------------------------

        ultima_version = db.execute(
            """
            SELECT MAX(version) AS version
            FROM historial_entregas
            WHERE entrega_id = ?
            """,
            (version_actual["entrega_id"],)
        ).fetchone()

        if ultima_version["version"] != version_actual["version"]:
            flash(
                "No puedes registrar la revisión de una versión anterior.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )
        
        # ----------------------------------------------------
        # BUSCAR VERSIÓN ANTERIOR
        # ----------------------------------------------------

        version_anterior = db.execute(
            """
            SELECT *
            FROM historial_entregas
            WHERE entrega_id = ?
              AND nivel = ?
              AND version < ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (
                version_actual["entrega_id"],
                version_actual["nivel"],
                version_actual["version"]
            )
        ).fetchone()

        if not version_anterior:
            flash("No existe una versión anterior.", "error")
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # OBTENER OBSERVACIONES VÁLIDAS
        # ----------------------------------------------------

        observaciones = db.execute(
            """
            SELECT id
            FROM observaciones_correccion
            WHERE historial_entrega_id = ?
            """,
            (version_anterior["id"],)
        ).fetchall()

        if not observaciones:
            flash("No existen observaciones para revisar.", "error")
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # OBTENER OBSERVACIONES MARCADAS COMO ATENDIDAS
        # ----------------------------------------------------

        ids_atendidas = set()

        for valor in request.form.getlist("atendidas"):

            try:
                ids_atendidas.add(int(valor))
            except (ValueError, TypeError):
                continue

        ids_validos = {
            observacion["id"]
            for observacion in observaciones
        }

        ids_atendidas = ids_atendidas.intersection(ids_validos)

        total = len(ids_validos)
        cantidad_atendidas = len(ids_atendidas)
        cantidad_pendientes = total - cantidad_atendidas

        # ----------------------------------------------------
        # GUARDAR ESTADO DE CADA OBSERVACIÓN
        # ----------------------------------------------------

        for observacion_id in ids_validos:

            estado_revision = (
                "Atendida"
                if observacion_id in ids_atendidas
                else "Pendiente"
            )

            db.execute(
                """
                UPDATE observaciones_correccion
                SET estado_revision = ?
                WHERE id = ?
                  AND historial_entrega_id = ?
                """,
                (
                    estado_revision,
                    observacion_id,
                    version_anterior["id"]
                )
            )

        # ----------------------------------------------------
        # GUARDAR RESUMEN DE LA REVISIÓN
        # ----------------------------------------------------

        db.execute(
            """
            INSERT INTO revisiones_correcciones (
                historial_anterior_id,
                historial_nuevo_id,
                tutor_id,
                total_observaciones,
                atendidas,
                pendientes
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT(historial_anterior_id, historial_nuevo_id)
            DO UPDATE SET
                tutor_id = excluded.tutor_id,
                total_observaciones = excluded.total_observaciones,
                atendidas = excluded.atendidas,
                pendientes = excluded.pendientes,
                registrado_en = CURRENT_TIMESTAMP
            """,
            (
                version_anterior["id"],
                version_actual["id"],
                usuario["id"],
                total,
                cantidad_atendidas,
                cantidad_pendientes
            )
        )

    flash(
        f"Revisión registrada: {cantidad_atendidas} atendidas "
        f"y {cantidad_pendientes} pendientes.",
        "exito"
    )

    return redirect(
        url_for(
            "comparador_correcciones",
            investigacion_id=investigacion_id,
            historial_id=historial_id
        )
    )


# ============================================================
# REVISAR NIVEL DE INVESTIGACIÓN
# ============================================================

@app.route(
    "/entregas/<int:entrega_id>/revisar",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def revisar_nivel(entrega_id):

    usuario = usuario_actual()

    # --------------------------------------------------------
    # DATOS DEL FORMULARIO
    # --------------------------------------------------------

    estado = request.form.get("estado", "").strip()

    observaciones = request.form.get(
        "observaciones", ""
    ).strip()

    observaciones_lista = request.form.get(
        "observaciones_lista", ""
    ).strip()

    nota_texto = request.form.get(
        "nota", ""
    ).strip()

    # --------------------------------------------------------
    # SEPARAR OBSERVACIONES INDIVIDUALES
    # --------------------------------------------------------

    if observaciones_lista:
        lista_observaciones = [
            linea.strip()
            for linea in observaciones_lista.splitlines()
            if linea.strip()
        ]

    else:
        lista_observaciones = [
            linea.strip()
            for linea in observaciones.splitlines()
            if linea.strip()
        ]

    # Mantener también un resumen general
    if lista_observaciones and not observaciones:
        observaciones = "\n".join(lista_observaciones)

    # --------------------------------------------------------
    # VALIDAR ESTADO
    # --------------------------------------------------------

    estados_validos = {
        "Aprobado",
        "Pendiente de revisión",
        "Necesita correcciones"
    }

    if estado not in estados_validos:
        flash("El estado de revisión no es válido.", "error")
        return redirect(url_for("panel"))

    # --------------------------------------------------------
    # VALIDAR OBSERVACIONES
    # --------------------------------------------------------

    if (
        estado == "Necesita correcciones"
        and not lista_observaciones
    ):
        flash(
            "Debes registrar al menos una observación para solicitar correcciones.",
            "error"
        )
        return redirect(url_for("panel"))

    # --------------------------------------------------------
    # VALIDAR NOTA
    # --------------------------------------------------------

    nota = None

    if nota_texto:
        try:
            nota = float(nota_texto)

            if nota < 0 or nota > 100:
                raise ValueError

        except ValueError:
            flash(
                "La nota debe ser un número entre 0 y 100.",
                "error"
            )
            return redirect(url_for("panel"))

    # --------------------------------------------------------
    # PROCESAR REVISIÓN
    # --------------------------------------------------------

    with conectar_db() as db:

        # Buscar entrega e investigación
        entrega = db.execute(
            """
            SELECT
                e.*,
                i.profesor_id,
                i.finalizada,
                i.nivel_actual,
                i.id AS investigacion_id,
                i.titulo AS investigacion_titulo,
                i.grupo_id
            FROM entregas e
            JOIN investigaciones i
                ON i.id = e.investigacion_id
            WHERE e.id = ?
            """,
            (entrega_id,)
        ).fetchone()

        if not entrega:
            flash("La entrega no existe.", "error")
            return redirect(url_for("panel"))

        investigacion_id = entrega["investigacion_id"]
        nivel = entrega["nivel"]

        # ----------------------------------------------------
        # VALIDAR QUE LA INVESTIGACIÓN NO ESTÉ FINALIZADA
        # ----------------------------------------------------

        if entrega["finalizada"]:
            flash(
                "Esta investigación ya fue finalizada.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # ----------------------------------------------------
        # VALIDAR ASIGNACIÓN DEL TUTOR
        # ----------------------------------------------------

        if (
            usuario["rol"] == "tutor"
            and entrega["profesor_id"] != usuario["id"]
        ):
            flash(
                "No tienes permiso para revisar esta investigación.",
                "error"
            )
            return redirect(url_for("panel"))

        # ----------------------------------------------------
        # ACTUALIZAR ENTREGA PRINCIPAL
        # ----------------------------------------------------

        db.execute(
            """
            UPDATE entregas
            SET
                estado = ?,
                comentario_profesor = ?,
                revisado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                estado,
                observaciones,
                entrega_id
            )
        )

        # ----------------------------------------------------
        # BUSCAR ÚLTIMA VERSIÓN DEL HISTORIAL
        # ----------------------------------------------------

        historial_actual = db.execute(
            """
            SELECT id
            FROM historial_entregas
            WHERE entrega_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (entrega_id,)
        ).fetchone()

        if historial_actual:

            historial_id = historial_actual["id"]

            # Actualizar la última versión
            db.execute(
                """
                UPDATE historial_entregas
                SET
                    estado = ?,
                    observaciones = ?,
                    nota = ?,
                    revisado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    estado,
                    observaciones,
                    nota,
                    historial_id
                )
            )

            # ------------------------------------------------
            # GUARDAR OBSERVACIONES INDIVIDUALES
            # ------------------------------------------------

            if estado == "Necesita correcciones":

                # Reemplazar observaciones de esta versión
                db.execute(
                    """
                    DELETE FROM observaciones_correccion
                    WHERE historial_entrega_id = ?
                    """,
                    (historial_id,)
                )

                # Registrar cada observación por separado
                for texto_observacion in lista_observaciones:

                    db.execute(
                        """
                        INSERT INTO observaciones_correccion (
                            historial_entrega_id,
                            texto
                        )
                        VALUES (?, ?)
                        """,
                        (
                            historial_id,
                            texto_observacion
                        )
                    )

        # ----------------------------------------------------
        # ACTUALIZAR ESTADO DEL NIVEL
        # ----------------------------------------------------

        db.execute(
            """
            UPDATE niveles_investigacion
            SET
                estado = ?,
                observaciones = ?,
                nota = ?,
                evaluado = ?,
                revisado_en = CURRENT_TIMESTAMP
            WHERE investigacion_id = ?
              AND nivel = ?
            """,
            (
                estado,
                observaciones,
                nota,
                0 if estado == "Pendiente de revisión" else 1,
                investigacion_id,
                nivel
            )
        )

        # ----------------------------------------------------
        # ACTUALIZAR INVESTIGACIÓN SEGÚN LA EVALUACIÓN
        # ----------------------------------------------------

        if estado == "Aprobado":

            nuevo_nivel = nivel + 1

            if nuevo_nivel > 6:
                nuevo_nivel = 6

            if nivel >= 6:

                db.execute(
                    """
                    UPDATE investigaciones
                    SET
                        estado = 'Finalizada',
                        finalizada = 1,
                        estado_evaluacion = 'Aprobado'
                    WHERE id = ?
                    """,
                    (investigacion_id,)
                )

            else:

                db.execute(
                    """
                    UPDATE investigaciones
                    SET
                        nivel_actual = ?,
                        estado = 'En desarrollo',
                        estado_evaluacion = 'Aprobado'
                    WHERE id = ?
                    """,
                    (
                        nuevo_nivel,
                        investigacion_id
                    )
                )

        elif estado == "Necesita correcciones":

            db.execute(
                """
                UPDATE investigaciones
                SET
                    estado = 'Correcciones pendientes',
                    estado_evaluacion = 'Correcciones'
                WHERE id = ?
                """,
                (investigacion_id,)
            )

        else:

            db.execute(
                """
                UPDATE investigaciones
                SET
                    estado = 'En revisión',
                    estado_evaluacion = 'En revisión'
                WHERE id = ?
                """,
                (investigacion_id,)
            )

        # ----------------------------------------------------
        # REGISTRAR EVENTO EN EL HISTORIAL DE PROGRESO
        # ----------------------------------------------------

        try:
            registrar_evento_progreso_db(
                db,
                investigacion_id,
                usuario["id"],
                f"El tutor revisó el Nivel {nivel}: {estado}."
            )
        except Exception:
            pass

        # ----------------------------------------------------
        # NOTIFICAR A LOS ESTUDIANTES DEL GRUPO
        # ----------------------------------------------------

        miembros = db.execute(
            """
            SELECT usuario_id
            FROM miembros_grupo
            WHERE grupo_id = ?
            """,
            (entrega["grupo_id"],)
        ).fetchall()

        mensaje = (
            f"Tu entrega del Nivel {nivel} "
            f"fue revisada: {estado}."
        )

        if estado == "Necesita correcciones":
            mensaje += " Revisa las observaciones del tutor y realiza las correcciones."

        elif estado == "Aprobado":
            mensaje += " ¡Puedes continuar con el siguiente nivel!"

        for miembro in miembros:

            try:
                crear_notificacion(
                    db,
                    miembro["usuario_id"],
                    mensaje,
                    url_for(
                        "detalle_investigacion",
                        investigacion_id=investigacion_id
                    )
                )
            except Exception:
                pass

    # --------------------------------------------------------
    # MENSAJE FINAL
    # --------------------------------------------------------

    if estado == "Aprobado":
        flash(
            "¡Entrega aprobada! Se actualizó el avance de la investigación.",
            "exito"
        )

    elif estado == "Necesita correcciones":
        flash(
            "Revisión guardada. Las observaciones se registraron individualmente.",
            "exito"
        )

    else:
        flash(
            "La revisión quedó pendiente.",
            "exito"
        )

    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
    )


# ============================================================
# RÚBRICAS DE EVALUACIÓN — GESTIÓN DE CRITERIOS
# ============================================================

@app.route("/evaluacion/rubricas")
@roles_requeridos("tutor")
def evaluacion_rubricas():

    usuario = usuario_actual()

    criterios_iniciales = [
        ("Planteamiento del problema", 20),
        ("Objetivos y coherencia", 20),
        ("Metodología", 25),
        ("Fuentes y citas (APA 7)", 20),
        ("Redacción y formato", 15)
    ]

    with conectar_db() as db:

        criterios = db.execute("""
            SELECT *
            FROM rubricas_criterios
            WHERE tutor_id = ? AND activo = 1
            ORDER BY orden ASC, id ASC
        """, (usuario["id"],)).fetchall()

        # Crear criterios iniciales si el tutor todavía no tiene rúbrica
        if not criterios:

            for orden, (nombre, puntaje) in enumerate(criterios_iniciales, 1):
                db.execute("""
                    INSERT INTO rubricas_criterios (
                        tutor_id, nombre, puntaje_maximo, orden
                    )
                    VALUES (?, ?, ?, ?)
                """, (usuario["id"], nombre, puntaje, orden))

            criterios = db.execute("""
                SELECT *
                FROM rubricas_criterios
                WHERE tutor_id = ? AND activo = 1
                ORDER BY orden ASC, id ASC
            """, (usuario["id"],)).fetchall()

        total_puntos = sum(
            float(c["puntaje_maximo"]) for c in criterios
        )

    return render_template(
        "evaluacion_rubricas.html",
        usuario=usuario,
        criterios=criterios,
        total_puntos=total_puntos
    )


# ============================================================
# AGREGAR CRITERIO
# ============================================================

@app.route("/evaluacion/rubricas/agregar", methods=["POST"])
@roles_requeridos("tutor")
def agregar_criterio_rubrica():

    usuario = usuario_actual()

    nombre = request.form.get("nombre", "").strip()
    puntaje_texto = request.form.get("puntaje_maximo", "").strip()

    if not nombre or not puntaje_texto:
        flash("Completa el nombre y el puntaje del criterio.", "error")
        return redirect(url_for("evaluacion_rubricas"))

    try:
        puntaje = float(puntaje_texto.replace(",", "."))
    except ValueError:
        flash("El puntaje debe ser un número válido.", "error")
        return redirect(url_for("evaluacion_rubricas"))

    if puntaje <= 0:
        flash("El puntaje debe ser mayor que cero.", "error")
        return redirect(url_for("evaluacion_rubricas"))

    with conectar_db() as db:

        resultado = db.execute("""
            SELECT COALESCE(SUM(puntaje_maximo), 0) AS total
            FROM rubricas_criterios
            WHERE tutor_id = ? AND activo = 1
        """, (usuario["id"],)).fetchone()

        total_actual = float(resultado["total"])

        if total_actual + puntaje > 100:
            flash(
                f"No puedes superar los 100 puntos. "
                f"Actualmente tienes {total_actual:g} puntos.",
                "error"
            )
            return redirect(url_for("evaluacion_rubricas"))

        orden = db.execute("""
            SELECT COALESCE(MAX(orden), 0) + 1 AS siguiente
            FROM rubricas_criterios
            WHERE tutor_id = ?
        """, (usuario["id"],)).fetchone()["siguiente"]

        db.execute("""
            INSERT INTO rubricas_criterios (
                tutor_id, nombre, puntaje_maximo, orden
            )
            VALUES (?, ?, ?, ?)
        """, (usuario["id"], nombre, puntaje, orden))

    flash("Criterio agregado correctamente.", "success")
    return redirect(url_for("evaluacion_rubricas"))


# ============================================================
# ELIMINAR CRITERIO
# ============================================================

@app.route(
    "/evaluacion/rubricas/eliminar/<int:criterio_id>",
    methods=["POST"]
)
@roles_requeridos("tutor")
def eliminar_criterio_rubrica(criterio_id):

    usuario = usuario_actual()

    with conectar_db() as db:

        criterio = db.execute("""
            SELECT id
            FROM rubricas_criterios
            WHERE id = ?
              AND tutor_id = ?
              AND activo = 1
        """, (criterio_id, usuario["id"])).fetchone()

        if not criterio:
            flash("No se encontró el criterio solicitado.", "error")
            return redirect(url_for("evaluacion_rubricas"))

        db.execute("""
            UPDATE rubricas_criterios
            SET activo = 0
            WHERE id = ? AND tutor_id = ?
        """, (criterio_id, usuario["id"]))

    flash("Criterio eliminado correctamente.", "success")
    return redirect(url_for("evaluacion_rubricas"))
    
# ============================================================
# CIERRE DEFINITIVO Y ARCHIVO DE MONOGRAFÍA
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/cerrar",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def cerrar_investigacion(investigacion_id):

    usuario = usuario_actual()
    archivo = request.files.get("archivo_final")

    if not archivo or not archivo.filename:
        flash(
            "Debes adjuntar el PDF completo de la monografía.",
            "error"
        )
        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )

    if not archivo.filename.lower().endswith(".pdf"):
        flash(
            "El documento final debe estar en formato PDF.",
            "error"
        )
        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )

    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            flash("Investigación no encontrada.", "error")
            return redirect(url_for("panel"))

        if investigacion["finalizada"]:
            flash(
                "Esta investigación ya fue finalizada.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        if (
            usuario["rol"] == "tutor"
            and investigacion["profesor_id"] != usuario["id"]
        ):
            flash(
                "No tienes permiso para cerrar esta investigación.",
                "error"
            )
            return redirect(url_for("panel"))

        if investigacion["estado"] != "Evaluación final":
            flash(
                "Primero deben aprobarse los seis niveles.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # Comprobar que los seis niveles estén aprobados.
        aprobados = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM niveles_investigacion
            WHERE investigacion_id = ?
              AND nivel BETWEEN 1 AND 6
              AND estado = 'Aprobado'
            """,
            (investigacion_id,)
        ).fetchone()["total"]

        if aprobados != 6:
            flash(
                "No se puede cerrar: los seis niveles deben estar aprobados.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # Preparar el vínculo con la investigación.
        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(recursos_biblioteca)"
            ).fetchall()
        }

        if "investigacion_id" not in columnas:
            db.execute(
                """
                ALTER TABLE recursos_biblioteca
                ADD COLUMN investigacion_id INTEGER
                """
            )

        # Evitar archivar dos veces la misma investigación.
        existente = db.execute(
            """
            SELECT id
            FROM recursos_biblioteca
            WHERE investigacion_id = ?
              AND tipo = 'Monografía'
            LIMIT 1
            """,
            (investigacion_id,)
        ).fetchone()

        if existente:
            flash(
                "Esta monografía ya está registrada en el archivo.",
                "error"
            )
            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )

        # Nombre seguro del archivo final.
        nombre_original = secure_filename(archivo.filename)

        nombre_final = (
            f"monografia_{investigacion_id}_{nombre_original}"
        )

        ruta_final = UPLOAD_DIR / nombre_final

        # Guardar el PDF en la carpeta de archivos existente.
        archivo.save(ruta_final)

        try:
            # Registrar la monografía en la biblioteca histórica.
            db.execute(
                """
                INSERT INTO recursos_biblioteca (
                    titulo,
                    descripcion,
                    tipo,
                    nivel,
                    area_principal,
                    subarea,
                    url,
                    archivo,
                    gestion,
                    creado_por,
                    creado_en,
                    investigacion_id
                )
                VALUES (
                    ?, ?, 'Monografía', 6, ?, ?, NULL, ?,
                    CAST(strftime('%Y', 'now', 'localtime') AS INTEGER),
                    ?, CURRENT_TIMESTAMP, ?
                )
                """,
                (
                    investigacion["titulo"],
                    "Monografía final aprobada.",
                    investigacion["area_principal"],
                    investigacion["subarea"],
                    nombre_final,
                    usuario["id"],
                    investigacion_id
                )
            )

            # Cerrar la investigación solo después de archivarla.
            db.execute(
                """
                UPDATE investigaciones
                SET
                    finalizada = 1,
                    estado = 'Finalizada',
                    estado_evaluacion = 'Aprobado',
                    nota_visible = 1
                WHERE id = ?
                """,
                (investigacion_id,)
            )

            registrar_evento_progreso_db(
                db,
                investigacion_id,
                6,
                "Monografía final aprobada y archivada"
            )

        except Exception:
            # Evitar dejar un archivo huérfano si falla el registro.
            if ruta_final.exists():
                ruta_final.unlink()
            raise

    flash(
        "¡Monografía finalizada y archivada correctamente!",
        "exito"
    )

    return redirect(
        url_for("biblioteca_monografias")
    )



# ============================================================
# RÚBRICA DIGITAL
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/rubrica",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def guardar_rubrica(
    investigacion_id
):

    usuario = usuario_actual()

    nivel = request.form.get(
        "nivel",
        type=int
    )

    if not nivel or not 1 <= nivel <= 6:

        flash(
            "Nivel de rúbrica inválido.",
            "error"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )


    criterios = []

    nombres = [
        "criterio1",
        "criterio2",
        "criterio3",
        "criterio4",
        "criterio5"
    ]


    try:

        for nombre in nombres:

            valor = int(
                request.form.get(
                    nombre,
                    0
                )
            )

            if not 0 <= valor <= 20:

                raise ValueError

            criterios.append(valor)

    except (ValueError, TypeError):

        flash(
            "Cada criterio debe tener una puntuación entre 0 y 20.",
            "error"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )


    observaciones = request.form.get(
        "observaciones",
        ""
    ).strip()

    puntaje = sum(
        criterios
    )


    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()


        if not investigacion:

            flash(
                "Investigación no encontrada.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        if (
            usuario["rol"] == "tutor"
            and
            investigacion["profesor_id"]
            !=
            usuario["id"]
        ):

            flash(
                "No tienes permiso.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        db.execute(
            """
            INSERT INTO rubricas
            (
                investigacion_id,
                nivel,
                evaluador_id,
                criterio1,
                criterio2,
                criterio3,
                criterio4,
                criterio5,
                observaciones,
                puntaje
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                investigacion_id,
                nivel,
                usuario["id"],
                criterios[0],
                criterios[1],
                criterios[2],
                criterios[3],
                criterios[4],
                observaciones,
                puntaje
            )
        )


    flash(
        f"Rúbrica guardada. Puntaje: {puntaje}/100.",
        "exito"
    )

    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
        + "#rubrica"
    )


# ============================================================
# COMENTARIOS / OBSERVACIONES
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/comentarios",
    methods=["POST"]
)
@login_requerido
def agregar_comentario(
    investigacion_id
):

    usuario = usuario_actual()

    mensaje = request.form.get(
        "mensaje",
        ""
    ).strip()


    if not mensaje:

        flash(
            "Escribe un mensaje.",
            "error"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )


    if len(mensaje) > 3000:

        flash(
            "El mensaje es demasiado largo.",
            "error"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )


    permitido = False


    if usuario["rol"] == "admin":

        permitido = True

    elif usuario["rol"] == "tutor":

        permitido = profesor_puede_ver(
            investigacion_id,
            usuario["id"]
        )

    else:

        permitido = es_miembro_investigacion(
            usuario["id"],
            investigacion_id
        )


    if not permitido:

        flash(
            "No tienes permiso.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    with conectar_db() as db:

        db.execute(
            """
            INSERT INTO comentarios
            (
                investigacion_id,
                autor_id,
                mensaje
            )
            VALUES (?, ?, ?)
            """,
            (
                investigacion_id,
                usuario["id"],
                mensaje
            )
        )


    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
        + "#interacciones"
    )


# ============================================================
# FUENTES
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/fuentes",
    methods=["POST"]
)
@login_requerido
def agregar_fuente(
    investigacion_id
):

    usuario = usuario_actual()


    if usuario["rol"] == "estudiante":

        permitido = es_miembro_investigacion(
            usuario["id"],
            investigacion_id
        )

    elif usuario["rol"] == "tutor":

        permitido = profesor_puede_ver(
            investigacion_id,
            usuario["id"]
        )

    else:

        permitido = True


    if not permitido:

        flash(
            "No tienes permiso.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    autor = request.form.get(
        "autor",
        ""
    ).strip()

    anio = request.form.get(
        "anio",
        ""
    ).strip()

    titulo = request.form.get(
        "titulo",
        ""
    ).strip()

    tipo = request.form.get(
        "tipo",
        ""
    ).strip()

    url_fuente = request.form.get(
        "url",
        ""
    ).strip()

    fecha_consulta = request.form.get(
        "fecha_consulta",
        ""
    ).strip()


    if not autor or not titulo:

        flash(
            "Autor y título son obligatorios.",
            "error"
        )

        return redirect(
            url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )


    with conectar_db() as db:

        existe = db.execute(
            """
            SELECT id
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()


        if not existe:

            flash(
                "Investigación no encontrada.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        db.execute(
            """
            INSERT INTO fuentes
            (
                investigacion_id,
                autor,
                anio,
                titulo,
                tipo,
                url,
                fecha_consulta
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                investigacion_id,
                autor,
                anio,
                titulo,
                tipo,
                url_fuente,
                fecha_consulta
            )
        )


    flash(
        "Fuente agregada.",
        "exito"
    )

    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
    )


# ============================================================
# TAREAS / CRONOGRAMA
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/tareas",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def crear_tarea(
    investigacion_id
):

    usuario = usuario_actual()


    titulo = request.form.get(
        "titulo",
        ""
    ).strip()

    descripcion = request.form.get(
        "descripcion",
        ""
    ).strip()

    fecha_limite = request.form.get(
        "fecha_limite",
        ""
    ).strip()


    with conectar_db() as db:

        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()


        if not investigacion:

            flash(
                "Investigación no encontrada.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        if (
            usuario["rol"] == "tutor"
            and
            investigacion["profesor_id"]
            !=
            usuario["id"]
        ):

            flash(
                "No tienes permiso.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        if not titulo:

            flash(
                "El título es obligatorio.",
                "error"
            )

            return redirect(
                url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                )
            )


        db.execute(
            """
            INSERT INTO tareas
            (
                investigacion_id,
                titulo,
                descripcion,
                fecha_limite,
                creada_por
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                investigacion_id,
                titulo,
                descripcion,
                fecha_limite or None,
                usuario["id"]
            )
        )


    flash(
        "Tarea agregada al cronograma.",
        "exito"
    )

    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        )
        + "#cronograma"
    )


# ============================================================
# GUARDAR Y EDITAR EVENTOS DEL CRONOGRAMA
# ============================================================

@app.route("/admin/cronograma/guardar", methods=["POST"])
@login_requerido
def guardar_evento_cronograma():

    usuario = usuario_actual()

    # SOLO EL ADMINISTRADOR PUEDE MODIFICAR EL CRONOGRAMA

    if usuario["rol"] != "admin":
        flash(
            "No tienes permiso para modificar el cronograma.",
            "error"
        )
        return redirect(url_for("cronograma"))

    # DATOS DEL FORMULARIO

    evento_id = request.form.get("evento_id", "").strip()
    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora_inicio = request.form.get("hora_inicio", "").strip()
    hora_fin = request.form.get("hora_fin", "").strip()
    tipo = request.form.get("tipo", "Hito").strip()

    tipos_permitidos = [
        "Hito",
        "Entrega",
        "Reunión",
        "Defensa"
    ]

    # VALIDACIONES

    if not titulo or not fecha:
        flash(
            "El título y la fecha son obligatorios.",
            "error"
        )
        return redirect(url_for("panel"))

    if tipo not in tipos_permitidos:
        flash(
            "El tipo de evento seleccionado no es válido.",
            "error"
        )
        return redirect(url_for("panel"))

    try:
        fecha_objeto = date.fromisoformat(fecha)
    except (ValueError, TypeError):
        flash(
            "La fecha introducida no es válida.",
            "error"
        )
        return redirect(url_for("panel"))

    # VALIDAR HORARIOS

    for hora in [hora_inicio, hora_fin]:

        if hora:
            try:
                partes = hora.split(":")

                if len(partes) != 2:
                    raise ValueError

                horas = int(partes[0])
                minutos = int(partes[1])

                if not (0 <= horas <= 23 and 0 <= minutos <= 59):
                    raise ValueError

            except (ValueError, TypeError):
                flash(
                    "Uno de los horarios introducidos no es válido.",
                    "error"
                )
                return redirect(url_for("panel"))

    if hora_fin and not hora_inicio:
        flash(
            "Debes indicar una hora de inicio.",
            "error"
        )
        return redirect(url_for("panel"))

    if hora_inicio and hora_fin and hora_fin <= hora_inicio:
        flash(
            "La hora de finalización debe ser posterior a la hora de inicio.",
            "error"
        )
        return redirect(url_for("panel"))

    try:

        with conectar_db() as db:

            # EDITAR EVENTO EXISTENTE

            if evento_id:

                if not evento_id.isdigit():
                    flash(
                        "El identificador del evento no es válido.",
                        "error"
                    )
                    return redirect(url_for("panel"))

                evento_existente = db.execute(
                    """
                    SELECT id
                    FROM eventos_cronograma
                    WHERE id = ?
                    """,
                    (int(evento_id),)
                ).fetchone()

                if not evento_existente:
                    flash(
                        "El evento que intentas editar no existe.",
                        "error"
                    )
                    return redirect(url_for("panel"))

                db.execute(
                    """
                    UPDATE eventos_cronograma
                    SET
                        titulo = ?,
                        descripcion = ?,
                        fecha = ?,
                        hora_inicio = ?,
                        hora_fin = ?,
                        tipo = ?,
                        modificada_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        titulo,
                        descripcion or None,
                        fecha,
                        hora_inicio or None,
                        hora_fin or None,
                        tipo,
                        int(evento_id)
                    )
                )

                flash(
                    "El evento se actualizó correctamente.",
                    "exito"
                )

            # CREAR EVENTO NUEVO

            else:

                db.execute(
                    """
                    INSERT INTO eventos_cronograma (
                        titulo,
                        descripcion,
                        fecha,
                        hora_inicio,
                        hora_fin,
                        tipo,
                        activa,
                        creada_por
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        titulo,
                        descripcion or None,
                        fecha,
                        hora_inicio or None,
                        hora_fin or None,
                        tipo,
                        usuario["id"]
                    )
                )

                flash(
                    "El evento se registró correctamente.",
                    "exito"
                )

    except sqlite3.IntegrityError:

        flash(
            "Ya existe un evento con ese mismo título y fecha.",
            "error"
        )

    except sqlite3.Error:

        flash(
            "Ocurrió un error al guardar el evento.",
            "error"
        )

    return redirect(url_for("panel"))


# ============================================================
# ELIMINAR EVENTOS DEL CRONOGRAMA
# ============================================================

@app.route(
    "/admin/cronograma/eliminar/<int:evento_id>",
    methods=["POST"]
)
@login_requerido
def eliminar_evento_cronograma(evento_id):

    usuario = usuario_actual()

    # SOLO EL ADMINISTRADOR PUEDE ELIMINAR EVENTOS

    if usuario["rol"] != "admin":
        flash(
            "No tienes permiso para eliminar eventos.",
            "error"
        )
        return redirect(url_for("cronograma"))

    try:

        with conectar_db() as db:

            resultado = db.execute(
                """
                DELETE FROM eventos_cronograma
                WHERE id = ?
                """,
                (evento_id,)
            )

            if resultado.rowcount == 0:
                flash(
                    "El evento que intentas eliminar no existe.",
                    "aviso"
                )
            else:
                flash(
                    "El evento fue eliminado correctamente.",
                    "exito"
                )

    except sqlite3.Error:

        flash(
            "No se pudo eliminar el evento.",
            "error"
        )

    return redirect(url_for("panel"))

# ============================================================
# COMPLETAR TAREA
# ============================================================

@app.route(
    "/tareas/<int:tarea_id>/completar",
    methods=["POST"]
)
@login_requerido
def completar_tarea(
    tarea_id
):

    usuario = usuario_actual()


    with conectar_db() as db:

        tarea = db.execute(
            """
            SELECT
                t.*,
                i.profesor_id,
                i.grupo_id
            FROM tareas t
            JOIN investigaciones i
                ON i.id = t.investigacion_id
            WHERE t.id = ?
            """,
            (tarea_id,)
        ).fetchone()


        if not tarea:

            flash(
                "Tarea no encontrada.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        permitido = (
            usuario["rol"] == "admin"
            or
            (
                usuario["rol"] == "tutor"
                and
                tarea["profesor_id"]
                ==
                usuario["id"]
            )
            or
            (
                usuario["rol"] == "estudiante"
                and
                es_miembro_investigacion(
                    usuario["id"],
                    tarea["investigacion_id"]
                )
            )
        )


        if not permitido:

            flash(
                "No tienes permiso.",
                "error"
            )

            return redirect(
                url_for("panel")
            )


        nuevo_estado = (
            0
            if tarea["completada"]
            else 1
        )


        db.execute(
            """
            UPDATE tareas
            SET completada = ?
            WHERE id = ?
            """,
            (
                nuevo_estado,
                tarea_id
            )
        )


    return redirect(
        url_for(
            "detalle_investigacion",
            investigacion_id=tarea["investigacion_id"]
        )
        + "#cronograma"
    )
# ------------------------------------------------------------
# MIGRACIÓN SEGURA DE PERMISOS DE LA BIBLIOTECA VIRTUAL
# Conserva los permisos y datos existentes.
# ------------------------------------------------------------

def asegurar_columnas_permisos_biblioteca():
    """Prepara y actualiza los permisos de la Biblioteca."""

    with conectar_db() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS permisos_biblioteca (
                tutor_id INTEGER PRIMARY KEY,
                puede_publicar INTEGER NOT NULL DEFAULT 1,
                puede_editar INTEGER NOT NULL DEFAULT 1,
                puede_eliminar INTEGER NOT NULL DEFAULT 1,
                puede_gestionar INTEGER NOT NULL DEFAULT 1,

                puede_publicar_guias INTEGER NOT NULL DEFAULT 1,
                puede_publicar_videos INTEGER NOT NULL DEFAULT 1,
                puede_publicar_ejemplos INTEGER NOT NULL DEFAULT 1,

                modificado_por INTEGER,
                modificado_en TEXT,

                FOREIGN KEY (tutor_id)
                    REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)

        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(permisos_biblioteca)"
            ).fetchall()
        }

        migraciones = {
            "puede_publicar": "INTEGER NOT NULL DEFAULT 1",
            "puede_editar": "INTEGER NOT NULL DEFAULT 1",
            "puede_eliminar": "INTEGER NOT NULL DEFAULT 1",
            "puede_gestionar": "INTEGER NOT NULL DEFAULT 1",

            "puede_publicar_guias": "INTEGER NOT NULL DEFAULT 1",
            "puede_publicar_videos": "INTEGER NOT NULL DEFAULT 1",
            "puede_publicar_ejemplos": "INTEGER NOT NULL DEFAULT 1",

            "modificado_por": "INTEGER",
            "modificado_en": "TEXT"
        }

        for columna, definicion in migraciones.items():

            if columna not in columnas:

                db.execute(
                    f"""
                    ALTER TABLE permisos_biblioteca
                    ADD COLUMN {columna} {definicion}
                    """
                )

        # Crear permisos para tutores nuevos.
        db.execute("""
            INSERT OR IGNORE INTO permisos_biblioteca (
                tutor_id,
                puede_publicar,
                puede_editar,
                puede_eliminar,
                puede_gestionar,
                puede_publicar_guias,
                puede_publicar_videos,
                puede_publicar_ejemplos
            )
            SELECT
                id, 1, 1, 1, 1, 1, 1, 1
            FROM usuarios
            WHERE rol = 'tutor'
              AND activo = 1
        """)


# ============================================================
# ADMINISTRACIÓN DE PERMISOS DE BIBLIOTECA
# ============================================================

@app.route(
    "/admin/biblioteca/permisos",
    methods=["GET", "POST"]
)
@login_requerido
def permisos_biblioteca_admin():

    usuario = usuario_actual()

    if usuario["rol"] != "admin":
        flash(
            "No tienes autorización para gestionar los permisos.",
            "error"
        )
        return redirect(url_for("panel"))

    asegurar_columnas_permisos_biblioteca()

    # ========================================================
    # GUARDAR CAMBIOS
    # ========================================================

    if request.method == "POST":

        tutor_id = request.form.get("tutor_id", type=int)

        if not tutor_id:
            flash("No se identificó al tutor.", "error")
            return redirect(url_for("permisos_biblioteca_admin"))

        campos = {
            "puede_publicar_guias": int(
                request.form.get("puede_publicar_guias") == "1"
            ),
            "puede_publicar_videos": int(
                request.form.get("puede_publicar_videos") == "1"
            ),
            "puede_publicar_ejemplos": int(
                request.form.get("puede_publicar_ejemplos") == "1"
            )
        }

        with conectar_db() as db:

            tutor = db.execute("""
                SELECT id
                FROM usuarios
                WHERE id = ?
                  AND rol = 'tutor'
                  AND activo = 1
            """, (tutor_id,)).fetchone()

            if not tutor:
                flash("El tutor seleccionado no existe.", "error")
                return redirect(url_for("permisos_biblioteca_admin"))

            db.execute("""
                INSERT OR IGNORE INTO permisos_biblioteca (
                    tutor_id
                )
                VALUES (?)
            """, (tutor_id,))

            db.execute("""
                UPDATE permisos_biblioteca
                SET
                    puede_publicar_guias = ?,
                    puede_publicar_videos = ?,
                    puede_publicar_ejemplos = ?,
                    modificado_por = ?,
                    modificado_en = CURRENT_TIMESTAMP
                WHERE tutor_id = ?
            """, (
                campos["puede_publicar_guias"],
                campos["puede_publicar_videos"],
                campos["puede_publicar_ejemplos"],
                usuario["id"],
                tutor_id
            ))

        flash(
            "Permisos del tutor actualizados correctamente.",
            "exito"
        )

        return redirect(url_for("permisos_biblioteca_admin"))

    # ========================================================
    # OBTENER TUTORES
    # ========================================================

    with conectar_db() as db:

        tutores = db.execute("""
            SELECT
                u.id,
                u.nombre,
                u.apellido,
                u.correo,

                COALESCE(p.puede_publicar_guias, 1)
                    AS puede_publicar_guias,

                COALESCE(p.puede_publicar_videos, 1)
                    AS puede_publicar_videos,

                COALESCE(p.puede_publicar_ejemplos, 1)
                    AS puede_publicar_ejemplos

            FROM usuarios u

            LEFT JOIN permisos_biblioteca p
                ON p.tutor_id = u.id

            WHERE u.rol = 'tutor'
              AND u.activo = 1

            ORDER BY u.apellido ASC, u.nombre ASC
        """).fetchall()

    return render_template(
        "permisos_biblioteca_admin.html",
        usuario=usuario,
        tutores=tutores
    )


def obtener_permisos_biblioteca(usuario):
    """
    El administrador tiene acceso completo.
    Los estudiantes solo consultan.
    Los tutores reciben únicamente los permisos asignados.
    """

    if usuario["rol"] == "admin":
        return {
            "puede_publicar": True,
            "puede_editar": True,
            "puede_eliminar": True,
            "puede_gestionar": True
        }

    permisos = {
        "puede_publicar": False,
        "puede_editar": False,
        "puede_eliminar": False,
        "puede_gestionar": False
    }

    if usuario["rol"] != "tutor":
        return permisos

    asegurar_columnas_permisos_biblioteca()

    with conectar_db() as db:
        registro = db.execute("""
            SELECT puede_publicar,
                   puede_editar,
                   puede_eliminar,
                   puede_gestionar
            FROM permisos_biblioteca
            WHERE tutor_id = ?
        """, (usuario["id"],)).fetchone()

    if registro:
        for nombre in permisos:
            permisos[nombre] = bool(registro[nombre])

    return permisos


# ------------------------------------------------------------
# DIRECTOR: GUARDAR PERMISOS INDIVIDUALES
# ------------------------------------------------------------


@app.route("/admin/permisos-biblioteca", methods=["POST"])
@roles_requeridos("admin")
def gestionar_permisos_biblioteca():
    asegurar_columnas_permisos_biblioteca()

    tutor_id = request.form.get("tutor_id", type=int)
    accion = request.form.get("accion", "").strip().lower()

    if not tutor_id or accion not in ("autorizar", "revocar"):
        flash("Solicitud de autorización no válida.", "error")
        return redirect(url_for("panel") + "#permisos-biblioteca")

    valor = 1 if accion == "autorizar" else 0

    try:
        with conectar_db() as db:
            tutor = db.execute("""
                SELECT id
                FROM usuarios
                WHERE id = ?
                  AND rol = 'tutor'
                  AND activo = 1
            """, (tutor_id,)).fetchone()

            if not tutor:
                flash("No se encontró un tutor activo.", "error")
                return redirect(
                    url_for("panel") + "#permisos-biblioteca"
                )

            existente = db.execute("""
                SELECT tutor_id
                FROM permisos_biblioteca
                WHERE tutor_id = ?
            """, (tutor_id,)).fetchone()

            if existente:
                db.execute("""
                    UPDATE permisos_biblioteca
                    SET puede_publicar = ?,
                        puede_editar = ?,
                        puede_eliminar = ?,
                        puede_gestionar = ?
                    WHERE tutor_id = ?
                """, (valor, valor, valor, valor, tutor_id))
            else:
                db.execute("""
                    INSERT INTO permisos_biblioteca (
                        tutor_id,
                        puede_publicar,
                        puede_editar,
                        puede_eliminar,
                        puede_gestionar
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (tutor_id, valor, valor, valor, valor))

            db.commit()

        if accion == "autorizar":
            flash(
                "Tutor APROBADO Y AUTORIZADO con los cuatro permisos.",
                "exito"
            )
        else:
            flash(
                "Se revocaron los cuatro permisos del tutor.",
                "exito"
            )

    except Exception:
        app.logger.exception(
            "Error al guardar permisos de Biblioteca Virtual"
        )
        flash(
            "Error al guardar los permisos. Revisa la terminal.",
            "error"
        )

    return redirect(url_for("panel") + "#permisos-biblioteca")






# ============================================================
# BIBLIOTECA VIRTUAL — PUBLICACIÓN Y CONSULTA
# ============================================================

@app.route("/biblioteca", methods=["GET", "POST"])
@login_requerido
def biblioteca():

    usuario = usuario_actual()

    asegurar_tabla_recursos_biblioteca()

    permisos = permisos_actuales_biblioteca(usuario)

    # ========================================================
    # OPCIONES VÁLIDAS
    # ========================================================

    tipos_validos = (
        "Guía",
        "Video",
        "Ejemplo",
        "Artículo",
        "Tesis"
    )

    areas_validas = (
        "General",
        "Ciencias sociales",
        "Matemática",
        "Ciencias naturales",
        "Lenguaje",
        "Psicología"
    )

    # ========================================================
    # PUBLICAR RECURSO
    # ========================================================

    if request.method == "POST":

        # Obtener información del formulario.
        titulo = request.form.get("titulo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        tipo = request.form.get("tipo", "").strip()
        autor = request.form.get("autor", "").strip()
        anio = request.form.get("anio_publicacion", "").strip()
        palabras_clave = request.form.get("palabras_clave", "").strip()
        cita_apa = request.form.get("cita_apa", "").strip()
        nivel = request.form.get("nivel", type=int)
        area = request.form.get("area_principal", "").strip()
        gestion = request.form.get("gestion", "").strip()
        url_recurso = request.form.get("url", "").strip()
        archivo = request.files.get("archivo")

        # ====================================================
        # VALIDAR INFORMACIÓN
        # ====================================================

        if not titulo:
            flash("El título es obligatorio.", "error")
            return redirect(url_for("biblioteca"))

        if tipo not in tipos_validos:
            flash(
                "Selecciona un tipo de recurso válido.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        # ====================================================
        # COMPROBAR PERMISOS INDIVIDUALES
        # ====================================================

        permisos_por_tipo = {
            "Guía": "puede_publicar_guias",
            "Video": "puede_publicar_videos",
            "Ejemplo": "puede_publicar_ejemplos"
        }

        if usuario["rol"] != "admin":

            # El permiso de gestión permite publicar cualquier tipo.
            if permisos.get("puede_gestionar", 0):
                autorizado = 1

            else:
                permiso_necesario = permisos_por_tipo.get(tipo)

                if permiso_necesario:
                    autorizado = permisos.get(permiso_necesario, 0)
                else:
                    autorizado = permisos.get("puede_publicar", 0)

            if not autorizado:
                flash(
                    "No tienes autorización para publicar este tipo de recurso.",
                    "error"
                )
                return redirect(url_for("biblioteca"))

        # ====================================================
        # VALIDAR ÁREA
        # ====================================================

        if area not in areas_validas:
            flash(
                "Selecciona un área válida.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        # ====================================================
        # VALIDAR NIVEL
        # ====================================================

        if nivel is not None and nivel not in range(1, 7):
            flash(
                "El nivel debe estar entre 1 y 6.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        # ====================================================
        # VALIDAR AÑO
        # ====================================================

        if anio and not anio.isdigit():
            flash(
                "El año de publicación debe contener números.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        # ====================================================
        # VALIDAR ENLACE
        # ====================================================

        if url_recurso and not url_recurso.lower().startswith(
            ("http://", "https://")
        ):
            flash(
                "El enlace debe comenzar con http:// o https://.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        # ====================================================
        # COMPROBAR ARCHIVO O ENLACE
        # ====================================================

        tiene_archivo = bool(
            archivo and archivo.filename
        )

        if not tiene_archivo and not url_recurso:
            flash(
                "Debes adjuntar un archivo o introducir un enlace.",
                "error"
            )
            return redirect(url_for("biblioteca"))

        nombre_archivo = None
        ruta_guardada = None

        # ====================================================
        # GUARDAR ARCHIVO
        # ====================================================

        if tiene_archivo:

            if not archivo_permitido(archivo.filename):
                flash(
                    "El formato del archivo no está permitido.",
                    "error"
                )
                return redirect(url_for("biblioteca"))

            partes = secure_filename(
                archivo.filename
            ).rsplit(".", 1)

            if len(partes) != 2:
                flash(
                    "El nombre del archivo no es válido.",
                    "error"
                )
                return redirect(url_for("biblioteca"))

            nombre_archivo = (
                f"{uuid.uuid4().hex}.{partes[1].lower()}"
            )

            UPLOAD_DIR.mkdir(
                parents=True,
                exist_ok=True
            )

            ruta_guardada = UPLOAD_DIR / nombre_archivo

            try:

                archivo.save(ruta_guardada)

            except Exception:

                app.logger.exception(
                    "Error al guardar archivo de Biblioteca"
                )

                flash(
                    "No se pudo guardar el archivo.",
                    "error"
                )

                return redirect(url_for("biblioteca"))

        # ====================================================
        # REGISTRAR RECURSO EN SQLITE
        # ====================================================

        try:

            with conectar_db() as db:

                db.execute("""
                    INSERT INTO recursos_biblioteca (
                        titulo,
                        descripcion,
                        tipo,
                        nivel,
                        area_principal,
                        url,
                        archivo,
                        gestion,
                        creado_por,
                        autor,
                        anio_publicacion,
                        palabras_clave,
                        cita_apa
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    titulo,
                    descripcion or None,
                    tipo,
                    nivel,
                    area,
                    url_recurso or None,
                    nombre_archivo,
                    gestion or None,
                    usuario["id"],
                    autor or None,
                    anio or None,
                    palabras_clave or None,
                    cita_apa or None
                ))

                db.commit()

        except Exception:

            if ruta_guardada and ruta_guardada.exists():
                ruta_guardada.unlink()

            app.logger.exception(
                "Error al publicar recurso académico"
            )

            flash(
                "No se pudo publicar el recurso. Revisa la terminal.",
                "error"
            )

            return redirect(url_for("biblioteca"))

        flash(
            "¡Recurso publicado correctamente!",
            "exito"
        )

        return redirect(url_for("biblioteca"))

    # ========================================================
    # BÚSQUEDA Y FILTROS
    # ========================================================

    busqueda = request.args.get("q", "").strip()
    area_filtro = request.args.get("area", "").strip()
    tipo_filtro = request.args.get("tipo", "").strip()
    nivel_filtro = request.args.get("nivel", type=int)

    consulta = """
        SELECT *
        FROM recursos_biblioteca
        WHERE 1 = 1
    """

    parametros = []

    # Buscar por título, autor, descripción o palabras clave.
    if busqueda:

        consulta += """
            AND (
                titulo LIKE ?
                OR autor LIKE ?
                OR descripcion LIKE ?
                OR palabras_clave LIKE ?
                OR anio_publicacion LIKE ?
                OR area_principal LIKE ?
                OR cita_apa LIKE ?
            )
        """

        termino = f"%{busqueda}%"

        parametros.extend([
            termino,
            termino,
            termino,
            termino,
            termino,
            termino,
            termino
        ])

    # Filtrar por área.
    if area_filtro in areas_validas:

        consulta += " AND area_principal = ?"

        parametros.append(area_filtro)

    # Filtrar por tipo.
    if tipo_filtro in tipos_validos:

        consulta += " AND tipo = ?"

        parametros.append(tipo_filtro)

    # Filtrar por nivel.
    if nivel_filtro and nivel_filtro in range(1, 7):

        consulta += " AND (nivel = ? OR nivel IS NULL)"

        parametros.append(nivel_filtro)

    # Ordenar recursos más recientes primero.
    consulta += " ORDER BY creado_en DESC, id DESC"

    # ========================================================
    # OBTENER RECURSOS
    # ========================================================

    with conectar_db() as db:

        recursos = db.execute(
            consulta,
            parametros
        ).fetchall()

    # ========================================================
    # MOSTRAR BIBLIOTECA
    # ========================================================

    return render_template(
        "biblioteca.html",
        usuario=usuario,
        recursos=recursos,
        permisos_biblioteca=permisos,
        nivel_filtro=nivel_filtro,
        area_filtro=area_filtro,
        tipo_filtro=tipo_filtro,
        busqueda=busqueda
    )



# ============================================================
# EDITAR UN RECURSO
# ============================================================

@app.route(
    "/biblioteca/editar/<int:recurso_id>",
    methods=["POST"]
)
@login_requerido
def editar_recurso_biblioteca(recurso_id):

    usuario = usuario_actual()
    asegurar_tabla_recursos_biblioteca()

    if not permiso_biblioteca_requerido(usuario, "puede_editar"):
        flash("No tienes permiso para editar recursos.", "error")
        return redirect(url_for("biblioteca"))

    with conectar_db() as db:
        recurso = db.execute("""
            SELECT *
            FROM recursos_biblioteca
            WHERE id = ?
        """, (recurso_id,)).fetchone()

    if not recurso:
        flash("El recurso no existe.", "error")
        return redirect(url_for("biblioteca"))

    titulo = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    tipo = request.form.get("tipo", "").strip()
    autor = request.form.get("autor", "").strip()
    anio = request.form.get("anio_publicacion", "").strip()
    palabras_clave = request.form.get("palabras_clave", "").strip()
    cita_apa = request.form.get("cita_apa", "").strip()
    area = request.form.get("area_principal", "").strip()
    url_recurso = request.form.get("url", "").strip()
    gestion = request.form.get("gestion", "").strip()

    tipos_validos = (
        "Guía",
        "Video",
        "Ejemplo",
        "Artículo",
        "Tesis"
    )

    areas_validas = (
        "General",
        "Ciencias sociales",
        "Matemática",
        "Ciencias naturales",
        "Lenguaje",
        "Psicología"
    )

    if not titulo:
            flash("El título es obligatorio.", "error")
            return redirect(url_for("biblioteca"))

    if tipo not in tipos_validos:
            flash("La categoría seleccionada no es válida.", "error")
            return redirect(url_for("biblioteca"))


        
    if area not in areas_validas:
        flash("El área seleccionada no es válida.", "error")
        return redirect(url_for("biblioteca"))

    if anio and not anio.isdigit():
        flash("El año debe contener solamente números.", "error")
        return redirect(url_for("biblioteca"))

    if url_recurso and not url_recurso.lower().startswith(
        ("https://", "http://")
    ):
        flash("El enlace debe comenzar con http:// o https://.", "error")
        return redirect(url_for("biblioteca"))

    archivo = request.files.get("archivo")
    nombre_archivo = recurso["archivo"]
    ruta_nueva = None

    if archivo and archivo.filename:

        if not archivo_permitido(archivo.filename):
            flash("El formato del archivo no está permitido.", "error")
            return redirect(url_for("biblioteca"))

        partes = secure_filename(archivo.filename).rsplit(".", 1)

        if len(partes) != 2:
            flash("El nombre del archivo no es válido.", "error")
            return redirect(url_for("biblioteca"))

        nombre_archivo = f"{uuid.uuid4().hex}.{partes[1].lower()}"

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        ruta_nueva = UPLOAD_DIR / nombre_archivo

        try:
            archivo.save(ruta_nueva)

        except Exception:
            app.logger.exception("Error al guardar archivo nuevo")
            flash("No se pudo guardar el archivo.", "error")
            return redirect(url_for("biblioteca"))

    try:

        with conectar_db() as db:

            db.execute("""
                UPDATE recursos_biblioteca
                SET titulo = ?,
                    descripcion = ?,
                    tipo = ?,
                    autor = ?,
                    anio_publicacion = ?,
                    palabras_clave = ?,
                    cita_apa = ?,
                    area_principal = ?,
                    url = ?,
                    archivo = ?,
                    gestion = ?
                WHERE id = ?
            """, (
                titulo,
                descripcion or None,
                tipo,
                autor or None,
                anio or None,
                palabras_clave or None,
                cita_apa or None,
                area,
                url_recurso or None,
                nombre_archivo,
                gestion or None,
                recurso_id
            ))

    except Exception:

        if ruta_nueva and ruta_nueva.exists():
            ruta_nueva.unlink()

        app.logger.exception("Error al editar recurso")
        flash("No se pudo actualizar el recurso.", "error")
        return redirect(url_for("biblioteca"))

    # Eliminar archivo anterior después de guardar el nuevo.
    archivo_anterior = recurso["archivo"]

    if ruta_nueva and archivo_anterior:

        nombre_anterior = secure_filename(archivo_anterior)
        ruta_anterior = UPLOAD_DIR / nombre_anterior

        if ruta_anterior.is_file():

            try:
                ruta_anterior.unlink()

            except OSError:
                app.logger.warning(
                    "No se pudo eliminar el archivo anterior del recurso %s",
                    recurso_id
                )

    flash("Recurso actualizado correctamente.", "exito")
    return redirect(url_for("biblioteca"))


# ============================================================
# ELIMINAR UN RECURSO
# ============================================================

@app.route(
    "/biblioteca/eliminar/<int:recurso_id>",
    methods=["POST"]
)
@login_requerido
def eliminar_recurso_biblioteca(recurso_id):

    usuario = usuario_actual()
    asegurar_tabla_recursos_biblioteca()

    if not permiso_biblioteca_requerido(usuario, "puede_eliminar"):
        flash("No tienes permiso para eliminar recursos.", "error")
        return redirect(url_for("biblioteca"))

    with conectar_db() as db:

        recurso = db.execute("""
            SELECT id, archivo
            FROM recursos_biblioteca
            WHERE id = ?
        """, (recurso_id,)).fetchone()

        if not recurso:
            flash("El recurso no existe.", "error")
            return redirect(url_for("biblioteca"))

        db.execute("""
            DELETE FROM recursos_biblioteca
            WHERE id = ?
        """, (recurso_id,))

    # Eliminar el archivo asociado.
    if recurso["archivo"]:

        nombre = secure_filename(recurso["archivo"])
        ruta = UPLOAD_DIR / nombre

        if ruta.is_file():

            try:
                ruta.unlink()

            except OSError:
                app.logger.warning(
                    "No se pudo eliminar el archivo del recurso %s",
                    recurso_id
                )

    flash("Recurso eliminado correctamente.", "exito")
    return redirect(url_for("biblioteca"))



# ------------------------------------------------------------
# PÁGINAS ESPECIALES DE LA BIBLIOTECA
# ------------------------------------------------------------


@app.route("/biblioteca/guias", methods=["GET", "POST"])
@login_requerido
def biblioteca_guias():
    import os
    import uuid
    from datetime import datetime
    from werkzeug.utils import secure_filename

    usuario = usuario_actual()
    usuario_id = usuario["id"]
    es_admin = usuario["rol"] == "admin"

    # =====================================================
    # PERMISOS DE BIBLIOTECA VIRTUAL
    # =====================================================

    permisos_biblioteca = {
        "puede_publicar": 0,
        "puede_editar": 0,
        "puede_eliminar": 0,
        "puede_gestionar": 0
    }

    puede_publicar = es_admin

    with conectar_db() as db:
        if not es_admin:
            tablas = {
                fila["name"]
                for fila in db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

            if "permisos_biblioteca" in tablas:
                columnas = {
                    fila["name"]
                    for fila in db.execute(
                        "PRAGMA table_info(permisos_biblioteca)"
                    ).fetchall()
                }

                columna_usuario = next(
                    (
                        nombre for nombre in ("usuario_id", "tutor_id", "id_usuario")
                        if nombre in columnas
                    ),
                    None
                )

                if columna_usuario:
                    permiso = db.execute(
                        f"""
                        SELECT *
                        FROM permisos_biblioteca
                        WHERE {columna_usuario} = ?
                        LIMIT 1
                        """,
                        (usuario_id,)
                    ).fetchone()

                    if permiso:
                        for nombre in permisos_biblioteca:
                            if nombre in columnas:
                                permisos_biblioteca[nombre] = int(
                                    permiso[nombre] or 0
                                )

                        puede_publicar = bool(
                            permisos_biblioteca["puede_publicar"]
                            or permisos_biblioteca["puede_gestionar"]
                        )

    # =====================================================
    # PUBLICAR DOCUMENTO O ENLACE
    # =====================================================

    if request.method == "POST":

        if not puede_publicar:
            flash(
                "No tienes permiso para publicar recursos en la Biblioteca Virtual.",
                "error"
            )
            return redirect(url_for("biblioteca_guias"))

        accion = request.form.get("accion", "").strip()
        tipo = request.form.get("tipo", "").strip()
        titulo = request.form.get("titulo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        nivel = request.form.get("nivel", "").strip()
        area_principal = request.form.get("area_principal", "").strip()

        if not titulo:
            flash("Escribe el título del recurso.", "error")
            return redirect(url_for("biblioteca_guias"))

        archivo_nombre = None
        url_recurso = None

        # -------------------------------------------------
        # PUBLICAR DOCUMENTO
        # -------------------------------------------------

        if accion == "publicar_documento":
            archivo = request.files.get("archivo")

            if not archivo or not archivo.filename:
                flash("Selecciona un archivo para publicar.", "error")
                return redirect(url_for("biblioteca_guias"))

            nombre_seguro = secure_filename(archivo.filename)
            extension = nombre_seguro.rsplit(".", 1)[-1].lower() if "." in nombre_seguro else ""

            extensiones_permitidas = {
                "pdf", "doc", "docx", "odt", "txt",
                "png", "jpg", "jpeg"
            }

            if extension not in extensiones_permitidas:
                flash(
                    "Formato no permitido. Usa PDF, DOC, DOCX, ODT, TXT, PNG, JPG o JPEG.",
                    "error"
                )
                return redirect(url_for("biblioteca_guias"))

            carpeta = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "static",
                "uploads"
            )
            os.makedirs(carpeta, exist_ok=True)

            archivo_nombre = f"{uuid.uuid4().hex}_{nombre_seguro}"
            ruta_archivo = os.path.join(carpeta, archivo_nombre)

            try:
                archivo.save(ruta_archivo)
            except Exception:
                flash("No se pudo guardar el archivo.", "error")
                return redirect(url_for("biblioteca_guias"))

            tipo = tipo or "Guía"

        # -------------------------------------------------
        # PUBLICAR ENLACE
        # -------------------------------------------------

        elif accion == "publicar_enlace":
            url_recurso = request.form.get("url", "").strip()

            if not url_recurso.startswith(("https://", "http://")):
                flash("Introduce un enlace válido que comience con http:// o https://.", "error")
                return redirect(url_for("biblioteca_guias"))

            tipo = tipo or "Video"

        else:
            flash("La acción solicitada no es válida.", "error")
            return redirect(url_for("biblioteca_guias"))

        # -------------------------------------------------
        # GUARDAR EN LA BASE DE DATOS
        # -------------------------------------------------

        try:
            with conectar_db() as db:
                columnas = {
                    fila["name"]
                    for fila in db.execute(
                        "PRAGMA table_info(recursos_biblioteca)"
                    ).fetchall()
                }

                datos = {
                    "titulo": titulo,
                    "descripcion": descripcion,
                    "tipo": tipo,
                    "nivel": nivel,
                    "area_principal": area_principal,
                    "archivo": archivo_nombre,
                    "url": url_recurso,
                    "creado_por": usuario_id,
                    "creado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                datos = {
                    nombre: valor
                    for nombre, valor in datos.items()
                    if nombre in columnas
                }

                nombres = list(datos.keys())
                campos_sql = ", ".join(f'"{nombre}"' for nombre in nombres)
                marcadores = ", ".join("?" for _ in nombres)

                db.execute(
                    f"""
                    INSERT INTO recursos_biblioteca ({campos_sql})
                    VALUES ({marcadores})
                    """,
                    tuple(datos[nombre] for nombre in nombres)
                )

            flash("¡Recurso publicado correctamente!", "success")

        except Exception as error:
            print("Error al publicar recurso de biblioteca:", error)
            flash(
                "No se pudo guardar el recurso. Revisa la terminal de Flask para ver el error.",
                "error"
            )

        return redirect(url_for("biblioteca_guias"))

    # =====================================================
    # MOSTRAR GUÍAS Y VIDEOS
    # =====================================================

    with conectar_db() as db:
        recursos = db.execute("""
            SELECT *
            FROM recursos_biblioteca
            WHERE tipo IN ('Guía', 'Video')
            ORDER BY nivel, creado_en DESC
        """).fetchall()

    return render_template(
        "biblioteca_guias.html",
        usuario=usuario,
        recursos=recursos,
        puede_publicar=puede_publicar,
        permisos_biblioteca=permisos_biblioteca
    )


@app.route("/biblioteca/monografias", methods=["GET", "POST"])
@login_requerido
def biblioteca_monografias():
    import os
    import uuid
    from datetime import datetime
    from werkzeug.utils import secure_filename
    from flask import (
        request, render_template, redirect, url_for,
        flash, current_app
    )

    usuario = usuario_actual()
    rol = usuario["rol"]

    # --------------------------------------------------
    # VERIFICAR PERMISOS
    # --------------------------------------------------
    def tiene_permiso(nombre_permiso):
        # El director tiene acceso completo.
        if rol == "admin":
            return True

        # Los estudiantes no publican ni eliminan.
        if rol != "tutor":
            return False

        with conectar_db() as db:
            columnas_usuarios = {
                fila["name"]
                for fila in db.execute(
                    "PRAGMA table_info(usuarios)"
                ).fetchall()
            }

            if nombre_permiso not in columnas_usuarios:
                return False

            # Buscar el campo de autorización general, si existe.
            campos_autorizacion = [
                "biblioteca_autorizado",
                "autorizado_biblioteca",
                "biblioteca_autorizada",
            ]

            campo_autorizacion = next(
                (
                    campo for campo in campos_autorizacion
                    if campo in columnas_usuarios
                ),
                None
            )

            campos = [nombre_permiso]
            if campo_autorizacion:
                campos.append(campo_autorizacion)

            consulta = (
                "SELECT "
                + ", ".join(f'"{campo}"' for campo in campos)
                + " FROM usuarios WHERE id = ?"
            )

            fila = db.execute(
                consulta, (usuario["id"],)
            ).fetchone()

            if not fila:
                return False

            if not fila[nombre_permiso]:
                return False

            if (
                campo_autorizacion
                and not fila[campo_autorizacion]
            ):
                return False

            return True

    puede_publicar = tiene_permiso("puede_publicar")
    puede_eliminar = tiene_permiso("puede_eliminar")

    # --------------------------------------------------
    # ARCHIVOS
    # --------------------------------------------------
    carpeta = os.path.join(
        current_app.static_folder,
        "uploads",
        "monografias"
    )
    os.makedirs(carpeta, exist_ok=True)

    # --------------------------------------------------
    # PROCESAR PUBLICACIÓN O ELIMINACIÓN
    # --------------------------------------------------
    if request.method == "POST":
        accion = request.form.get("accion", "publicar")

        if accion == "publicar":
            if not puede_publicar:
                flash(
                    "No tienes permiso para publicar monografías.",
                    "error"
                )
                return redirect(url_for("biblioteca_monografias"))

            titulo = request.form.get("titulo", "").strip()
            descripcion = request.form.get("descripcion", "").strip()
            gestion_texto = request.form.get("gestion", "").strip()
            archivo = request.files.get("archivo")

            if not titulo or not archivo or not archivo.filename:
                flash(
                    "Completa el título y selecciona un PDF.",
                    "error"
                )
                return redirect(url_for("biblioteca_monografias"))

            if not archivo.filename.lower().endswith(".pdf"):
                flash("Solo se permiten archivos PDF.", "error")
                return redirect(url_for("biblioteca_monografias"))

            try:
                gestion = int(gestion_texto)
                if gestion < 2000 or gestion > 2100:
                    raise ValueError
            except (ValueError, TypeError):
                flash(
                    "Introduce una gestión válida, por ejemplo 2025.",
                    "error"
                )
                return redirect(url_for("biblioteca_monografias"))

            nombre_original = secure_filename(archivo.filename)
            nombre_archivo = f"{uuid.uuid4().hex}_{nombre_original}"
            ruta_completa = os.path.join(carpeta, nombre_archivo)
            ruta_relativa = f"uploads/monografias/{nombre_archivo}"

            try:
                with conectar_db() as db:
                    columnas = {
                        fila["name"]
                        for fila in db.execute(
                            "PRAGMA table_info(recursos_biblioteca)"
                        ).fetchall()
                    }

                    if not {"id", "titulo", "tipo"}.issubset(columnas):
                        raise RuntimeError(
                            "La tabla recursos_biblioteca debe tener "
                            "las columnas id, titulo y tipo."
                        )

                    datos = {
                        "titulo": titulo,
                        "tipo": "Monografía",
                        "descripcion": descripcion,
                        "gestion": gestion,
                        "anio": gestion,
                        "archivo": ruta_relativa,
                        "url": ruta_relativa,
                        "creado_en": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "usuario_id": usuario["id"],
                        "subido_por": usuario["id"],
                    }

                    # Insertar solo campos que existan realmente.
                    datos = {
                        campo: valor
                        for campo, valor in datos.items()
                        if campo in columnas
                    }

                    # Debe existir un campo donde guardar el archivo.
                    if "archivo" not in columnas and "url" not in columnas:
                        raise RuntimeError(
                            "La tabla no tiene la columna archivo ni url."
                        )

                    # Si existen ambas columnas, se guarda la ruta en ambas.
                    if "archivo" in columnas:
                        datos["archivo"] = ruta_relativa
                    if "url" in columnas:
                        datos["url"] = ruta_relativa

                    archivo.save(ruta_completa)

                    campos_sql = ", ".join(
                        f'"{campo}"' for campo in datos
                    )
                    marcadores = ", ".join("?" for _ in datos)

                    db.execute(
                        f"INSERT INTO recursos_biblioteca "
                        f"({campos_sql}) VALUES ({marcadores})",
                        tuple(datos.values())
                    )

                flash("¡Monografía publicada correctamente!", "success")

            except Exception:
                if os.path.exists(ruta_completa):
                    os.remove(ruta_completa)

                current_app.logger.exception(
                    "No se pudo publicar la monografía"
                )
                flash(
                    "No se pudo publicar. Revisa el error en la consola "
                    "de Flask.",
                    "error"
                )

            return redirect(url_for("biblioteca_monografias"))

        elif accion == "eliminar":
            if not puede_eliminar:
                flash(
                    "No tienes permiso para eliminar monografías.",
                    "error"
                )
                return redirect(url_for("biblioteca_monografias"))

            try:
                recurso_id = int(request.form.get("recurso_id", ""))

                with conectar_db() as db:
                    recurso = db.execute(
                        """
                        SELECT *
                        FROM recursos_biblioteca
                        WHERE id = ? AND tipo = ?
                        """,
                        (recurso_id, "Monografía")
                    ).fetchone()

                    if not recurso:
                        flash("La monografía no existe.", "error")
                        return redirect(
                            url_for("biblioteca_monografias")
                        )

                    # Guardar la ruta del archivo antes de eliminar el registro.
                    columnas = recurso.keys()
                    ruta_guardada = (
                        recurso["archivo"]
                        if "archivo" in columnas and recurso["archivo"]
                        else recurso["url"]
                        if "url" in columnas and recurso["url"]
                        else None
                    )

                    db.execute(
                        "DELETE FROM recursos_biblioteca WHERE id = ?",
                        (recurso_id,)
                    )

                # Eliminar solo archivos dentro de la carpeta de monografías.
                if ruta_guardada and not ruta_guardada.startswith("http"):
                    ruta_limpia = ruta_guardada.replace("\\", "/")
                    prefijo = "uploads/monografias/"

                    if ruta_limpia.startswith(prefijo):
                        nombre = os.path.basename(ruta_limpia)
                        ruta_archivo = os.path.join(carpeta, nombre)

                        if os.path.isfile(ruta_archivo):
                            os.remove(ruta_archivo)

                flash("Monografía eliminada correctamente.", "success")

            except (ValueError, TypeError):
                flash("El identificador de la monografía no es válido.", "error")
            except Exception:
                current_app.logger.exception(
                    "No se pudo eliminar la monografía"
                )
                flash("No se pudo eliminar la monografía.", "error")

            return redirect(url_for("biblioteca_monografias"))

        flash("Acción no reconocida.", "error")
        return redirect(url_for("biblioteca_monografias"))

  
    # --------------------------------------------------
    # LISTAR MONOGRAFÍAS Y VALIDAR LAS AUTOMÁTICAS
    # --------------------------------------------------

    with conectar_db() as db:

        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(recursos_biblioteca)"
            ).fetchall()
        }

        orden = []

        if "gestion" in columnas:
            orden.append("r.gestion DESC")

        if "creado_en" in columnas:
            orden.append("r.creado_en DESC")

        orden_sql = ", ".join(orden) if orden else "r.rowid DESC"

        if "investigacion_id" in columnas:

            recursos = db.execute(f"""
                SELECT r.*
                FROM recursos_biblioteca r
                LEFT JOIN investigaciones i
                    ON i.id = r.investigacion_id
                WHERE r.tipo = ?
                  AND (
                      r.investigacion_id IS NULL
                      OR (
                          i.id IS NOT NULL
                          AND i.finalizada = 1
                          AND i.estado_evaluacion = 'Aprobado'
                      )
                  )
                ORDER BY {orden_sql}
            """, ("Monografía",)).fetchall()

        else:
            # Antes de existir la columna de vinculación,
            # solo se pueden listar los recursos manuales.
            recursos = db.execute(f"""
                SELECT r.*
                FROM recursos_biblioteca r
                WHERE r.tipo = ?
                ORDER BY {orden_sql}
            """, ("Monografía",)).fetchall()

    return render_template(
        "biblioteca_monografias.html",
        usuario=usuario,
        recursos=recursos,
        puede_publicar=puede_publicar,
        puede_eliminar=puede_eliminar
    )


@app.route("/biblioteca/ejemplos")
@login_requerido
def biblioteca_ejemplos():

    with conectar_db() as db:
        recursos = db.execute("""
            SELECT *
            FROM recursos_biblioteca
            WHERE tipo = 'Ejemplo'
            ORDER BY nivel, creado_en DESC
        """).fetchall()

    return render_template(
        "biblioteca_ejemplos.html",
        usuario=usuario_actual(),
        recursos=recursos
    )


@app.route("/biblioteca/fuentes")
@login_requerido
def biblioteca_fuentes():

    with conectar_db() as db:
        recursos = db.execute("""
            SELECT *
            FROM recursos_biblioteca
            WHERE tipo IN ('Fuente', 'Material')
            ORDER BY creado_en DESC
        """).fetchall()

    return render_template(
        "biblioteca_fuentes.html",
        usuario=usuario_actual(),
        recursos=recursos
    )


# ============================================================
# PERFIL
# ============================================================

@app.route(
    "/perfil",
    methods=["GET", "POST"]
)
@login_requerido
def perfil():

    usuario = usuario_actual()


    if request.method == "POST":

        password_actual = request.form.get(
            "password_actual",
            ""
        )

        password_nueva = request.form.get(
            "password_nueva",
            ""
        )

        password_repetir = request.form.get(
            "password_repetir",
            ""
        )


        with conectar_db() as db:

            fila = db.execute(
                """
                SELECT password_hash
                FROM usuarios
                WHERE id = ?
                """,
                (usuario["id"],)
            ).fetchone()


            if not fila:

                flash(
                    "Usuario no encontrado.",
                    "error"
                )

            elif not check_password_hash(
                fila["password_hash"],
                password_actual
            ):

                flash(
                    "La contraseña actual no es correcta.",
                    "error"
                )


            elif len(password_nueva) < 8:

                flash(
                    "La nueva contraseña debe tener al menos 8 caracteres.",
                    "error"
                )


            elif password_nueva != password_repetir:

                flash(
                    "Las contraseñas no coinciden.",
                    "error"
                )


            else:

                db.execute(
                    """
                    UPDATE usuarios
                    SET password_hash = ?
                    WHERE id = ?
                    """,
                    (
                        generate_password_hash(
                            password_nueva
                        ),
                        usuario["id"]
                    )
                )


                flash(
                    "Contraseña actualizada.",
                    "exito"
                )

                return redirect(
                    url_for("perfil")
                )


    return render_template(
        "perfil.html",
        usuario=usuario
    )


# ============================================================
# ESPECIALIDADES DEL PROFESOR
# ============================================================

@app.route(
    "/especialidades",
    methods=["GET", "POST"]
)
@roles_requeridos("admin", "tutor")
def especialidades():

    usuario = usuario_actual()


    if request.method == "POST":

        especialidad = request.form.get(
            "especialidad",
            ""
        ).strip()


        if especialidad:

            with conectar_db() as db:

                existe = db.execute(
                    """
                    SELECT id
                    FROM especialidades_catalogo
                    WHERE nombre = ?
                    """,
                    (especialidad,)
                ).fetchone()


                if not existe:

                    flash(
                        "La especialidad seleccionada no existe.",
                        "error"
                    )

                else:

                    db.execute(
                        """
                        INSERT OR IGNORE INTO
                        especialidades_tutor
                        (
                            tutor_id,
                            especialidad
                        )
                        VALUES (?, ?)
                        """,
                        (
                            usuario["id"],
                            especialidad
                        )
                    )


                    flash(
                        "Especialidad agregada.",
                        "exito"
                    )


    with conectar_db() as db:

        lista = db.execute(
            """
            SELECT *
            FROM especialidades_tutor
            WHERE tutor_id = ?
            ORDER BY especialidad
            """,
            (usuario["id"],)
        ).fetchall()


        catalogo = db.execute(
            """
            SELECT *
            FROM especialidades_catalogo
            ORDER BY nombre
            """
        ).fetchall()


    return render_template(
        "especialidades.html",
        especialidades=lista,
        catalogo=catalogo
    )


# ============================================================
# CHAT / INTERACCIONES
# ============================================================

@app.route(
    "/interacciones/<int:investigacion_id>"
)
@login_requerido
def interacciones(
    investigacion_id
):

    usuario = usuario_actual()


    permitido = (
        usuario["rol"] == "admin"
        or
        (
            usuario["rol"] == "tutor"
            and
            profesor_puede_ver(
                investigacion_id,
                usuario["id"]
            )
        )
        or
        (
            usuario["rol"] == "estudiante"
            and
            es_miembro_investigacion(
                usuario["id"],
                investigacion_id
            )
        )
    )


    if not permitido:

        flash(
            "No tienes permiso.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    with conectar_db() as db:

        mensajes = db.execute(
            """
            SELECT
                m.*,
                u.nombre,
                u.apellido,
                u.rol
            FROM mensajes_chat m
            JOIN usuarios u
                ON u.id = m.autor_id
            WHERE m.investigacion_id = ?
            ORDER BY m.creado_en
            """,
            (investigacion_id,)
        ).fetchall()


        investigacion = db.execute(
            """
            SELECT *
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()


    return render_template(
        "interacciones.html",
        mensajes=mensajes,
        investigacion=investigacion,
        investigacion_id=investigacion_id
    )


# ============================================================
# ENVIAR MENSAJE
# ============================================================

@app.route(
    "/interacciones/<int:investigacion_id>/enviar",
    methods=["POST"]
)
@login_requerido
def enviar_mensaje(
    investigacion_id
):

    usuario = usuario_actual()

    mensaje = request.form.get(
        "mensaje",
        ""
    ).strip()


    if not mensaje:

        return redirect(
            url_for(
                "interacciones",
                investigacion_id=investigacion_id
            )
        )


    if len(mensaje) > 3000:

        flash(
            "El mensaje es demasiado largo.",
            "error"
        )

        return redirect(
            url_for(
                "interacciones",
                investigacion_id=investigacion_id
            )
        )


    permitido = (
        usuario["rol"] == "admin"
        or
        (
            usuario["rol"] == "tutor"
            and
            profesor_puede_ver(
                investigacion_id,
                usuario["id"]
            )
        )
        or
        (
            usuario["rol"] == "estudiante"
            and
            es_miembro_investigacion(
                usuario["id"],
                investigacion_id
            )
        )
    )


    if not permitido:

        flash(
            "No tienes permiso.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    with conectar_db() as db:

        db.execute(
            """
            INSERT INTO mensajes_chat
            (
                investigacion_id,
                autor_id,
                mensaje
            )
            VALUES (?, ?, ?)
            """,
            (
                investigacion_id,
                usuario["id"],
                mensaje
            )
        )


    return redirect(
        url_for(
            "interacciones",
            investigacion_id=investigacion_id
        )
    )


# ============================================================
# SOLICITAR REUNIÓN
# DESDE NIVEL 2
# ============================================================


# ============================================================
# SOLICITAR REUNIÓN — GUARDAR Y NOTIFICAR AL TUTOR
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/reunion",
    methods=["POST"]
)
@roles_requeridos("estudiante")
def solicitar_reunion(investigacion_id):

    usuario = usuario_actual()

    if not es_miembro_investigacion(
        usuario["id"],
        investigacion_id
    ):
        flash("No tienes permiso.", "error")
        return redirect(url_for("panel"))

    motivo = request.form.get("motivo", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    duracion = request.form.get("duracion", type=int) or 30

    if duracion not in (15, 30, 45, 60):
        duracion = 30

    if not motivo or not fecha or not hora:
        flash("Completa motivo, fecha y hora.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    try:
        with conectar_db() as db:

            investigacion = db.execute(
                """
                SELECT id, titulo, profesor_id, nivel_actual
                FROM investigaciones
                WHERE id = ?
                """,
                (investigacion_id,)
            ).fetchone()

            if not investigacion:
                flash("Investigación no encontrada.", "error")
                return redirect(url_for("panel"))

            if investigacion["nivel_actual"] < 2:
                flash(
                    "La función de reuniones se habilita desde el Capítulo I.",
                    "aviso"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # 1. Guardar la solicitud de reunión.
            cursor = db.execute(
                """
                INSERT INTO solicitudes_reunion (
                    investigacion_id,
                    estudiante_id,
                    motivo,
                    fecha_solicitada,
                    hora_solicitada,
                    duracion
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    investigacion_id,
                    usuario["id"],
                    motivo,
                    fecha,
                    hora,
                    duracion
                )
            )

            reunion_id = cursor.lastrowid

            # 2. Preparar la notificación.
            enlace = url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )

            titulo_aviso = "Nueva solicitud de reunión"

            mensaje_aviso = (
                f"El estudiante {usuario['nombre']} solicitó "
                f"una reunión para la investigación "
                f"«{investigacion['titulo']}». "
                f"Fecha: {fecha}. Hora: {hora}. "
                f"Duración: {duracion} minutos. "
                f"Motivo: {motivo}"
            )

            # 3. Notificar al tutor asignado.
            tutor_id = investigacion["profesor_id"]

            if tutor_id:
                creada = crear_notificacion(
                    db=db,
                    usuario_id=tutor_id,
                    titulo=titulo_aviso,
                    mensaje=mensaje_aviso,
                    investigacion_id=investigacion_id,
                    enlace=enlace
                )

                if not creada:
                    raise RuntimeError(
                        "No se pudo guardar la notificación del tutor."
                    )

                app.logger.info(
                    "Notificación de reunión creada. "
                    "Reunión=%s, tutor=%s, investigación=%s",
                    reunion_id,
                    tutor_id,
                    investigacion_id
                )

            else:
                # Si todavía no hay tutor, avisar a los administradores.
                administradores = db.execute(
                    """
                    SELECT id
                    FROM usuarios
                    WHERE rol = 'admin'
                      AND activo = 1
                    """
                ).fetchall()

                for administrador in administradores:
                    creada = crear_notificacion(
                        db=db,
                        usuario_id=administrador["id"],
                        titulo="Solicitud de reunión sin tutor asignado",
                        mensaje=(
                            f"{mensaje_aviso} "
                            "Esta investigación todavía no tiene "
                            "un tutor asignado."
                        ),
                        investigacion_id=investigacion_id,
                        enlace=enlace
                    )

                    if not creada:
                        raise RuntimeError(
                            "No se pudo guardar la notificación "
                            "del administrador."
                        )

                app.logger.info(
                    "Solicitud de reunión sin tutor. "
                    "Reunión=%s, administradores avisados=%s",
                    reunion_id,
                    len(administradores)
                )

        flash(
            "Solicitud de reunión enviada y notificación registrada.",
            "exito"
        )

    except Exception:
        app.logger.exception(
            "Error al crear la solicitud o su notificación. "
            "Investigación=%s",
            investigacion_id
        )
        flash(
            "No se pudo registrar la solicitud y su notificación. "
            "Revisa la consola de Python.",
            "error"
        )

    return redirect(url_for(
        "detalle_investigacion",
        investigacion_id=investigacion_id
    ))




@app.route("/reuniones/<int:reunion_id>/responder", methods=["POST"])
@roles_requeridos("admin", "tutor")
def responder_reunion(reunion_id):
    usuario = usuario_actual()

    estado = request.form.get("estado", "").strip()
    respuesta = request.form.get("respuesta", "").strip()
    fecha_propuesta = request.form.get("fecha_propuesta", "").strip()
    hora_propuesta = request.form.get("hora_propuesta", "").strip()
    enlace_meet = request.form.get("enlace_meet", "").strip()

    estados_validos = ("Aceptada", "Rechazada", "Nueva propuesta")

    if estado not in estados_validos:
        flash("La opción seleccionada no es válida.", "error")
        return redirect(url_for("panel"))

    if estado == "Aceptada":
        if not enlace_meet.startswith("https://meet.google.com/"):
            flash(
                "Pegá un enlace válido de Google Meet para aceptar.",
                "error"
            )
            return redirect(url_for("panel"))

    if estado == "Nueva propuesta":
        if not fecha_propuesta or not hora_propuesta or not respuesta:
            flash(
                "Completá la nueva fecha, hora y respuesta.",
                "error"
            )
            return redirect(url_for("panel"))

    with conectar_db() as db:
        reunion = db.execute("""
            SELECT sr.*,
                   i.profesor_id,
                   i.titulo AS investigacion_titulo
            FROM solicitudes_reunion sr
            JOIN investigaciones i ON i.id = sr.investigacion_id
            WHERE sr.id = ?
        """, (reunion_id,)).fetchone()

        if not reunion:
            flash("La solicitud de reunión no existe.", "error")
            return redirect(url_for("panel"))

        if (
            usuario["rol"] == "tutor"
            and reunion["profesor_id"] != usuario["id"]
        ):
            flash("No tienes permiso para responder esta reunión.", "error")
            return redirect(url_for("panel"))

        investigacion_id = reunion["investigacion_id"]

        if not respuesta:
            if estado == "Aceptada":
                respuesta = "El tutor aceptó la reunión."
            elif estado == "Rechazada":
                respuesta = "El tutor rechazó la reunión."

        if estado == "Nueva propuesta":
            db.execute("""
                UPDATE solicitudes_reunion
                SET estado = ?,
                    respuesta_profesor = ?,
                    fecha_solicitada = ?,
                    hora_solicitada = ?
                WHERE id = ?
            """, (
                estado, respuesta, fecha_propuesta,
                hora_propuesta, reunion_id
            ))
            fecha_final = fecha_propuesta
            hora_final = hora_propuesta

        elif estado == "Aceptada":
            db.execute("""
                UPDATE solicitudes_reunion
                SET estado = ?,
                    respuesta_profesor = ?,
                    enlace_meet = ?
                WHERE id = ?
            """, (estado, respuesta, enlace_meet, reunion_id))

            fecha_final = reunion["fecha_solicitada"]
            hora_final = reunion["hora_solicitada"]

        else:
            db.execute("""
                UPDATE solicitudes_reunion
                SET estado = ?,
                    respuesta_profesor = ?,
                    enlace_meet = NULL
                WHERE id = ?
            """, (estado, respuesta, reunion_id))

            fecha_final = reunion["fecha_solicitada"]
            hora_final = reunion["hora_solicitada"]

        if estado == "Aceptada":
            titulo_aviso = "Reunión aceptada"
            mensaje_aviso = (
                f"Tu reunión para «{reunion['investigacion_titulo']}» "
                f"fue aceptada. Fecha: {fecha_final}. "
                f"Hora: {hora_final}. "
                f"Entrá a AulaInvestiga para acceder a Google Meet."
            )
        elif estado == "Rechazada":
            titulo_aviso = "Solicitud de reunión rechazada"
            mensaje_aviso = (
                f"Tu solicitud para «{reunion['investigacion_titulo']}» "
                f"fue rechazada. Respuesta: {respuesta}"
            )
        else:
            titulo_aviso = "Nueva propuesta de reunión"
            mensaje_aviso = (
                f"El tutor propuso una nueva fecha para "
                f"«{reunion['investigacion_titulo']}». "
                f"Fecha: {fecha_final}. Hora: {hora_final}. "
                f"Respuesta: {respuesta}"
            )

        creada = crear_notificacion(
            db=db,
            usuario_id=reunion["estudiante_id"],
            titulo=titulo_aviso,
            mensaje=mensaje_aviso,
            investigacion_id=investigacion_id,
            enlace=url_for(
                "detalle_investigacion",
                investigacion_id=investigacion_id
            )
        )

        if not creada:
            raise RuntimeError(
                "No se pudo registrar la notificación al estudiante."
            )

    flash("Respuesta guardada y notificación enviada.", "exito")
    return redirect(url_for(
        "detalle_investigacion",
        investigacion_id=investigacion_id
    ))



@app.route("/reuniones/<int:reunion_id>/entrar")
@login_requerido
def entrar_reunion(reunion_id):
    usuario = usuario_actual()

    with conectar_db() as db:
        reunion = db.execute("""
            SELECT sr.id,
                   sr.investigacion_id,
                   sr.estudiante_id,
                   sr.estado,
                   sr.enlace_meet,
                   i.profesor_id
            FROM solicitudes_reunion sr
            JOIN investigaciones i
                ON i.id = sr.investigacion_id
            WHERE sr.id = ?
        """, (reunion_id,)).fetchone()

    if not reunion:
        flash("La reunión no existe.", "error")
        return redirect(url_for("panel"))

    autorizado = (
        usuario["rol"] == "admin"
        or (
            usuario["rol"] == "estudiante"
            and usuario["id"] == reunion["estudiante_id"]
        )
        or (
            usuario["rol"] == "tutor"
            and usuario["id"] == reunion["profesor_id"]
        )
    )

    if not autorizado:
        flash("No tienes permiso para entrar a esta reunión.", "error")
        return redirect(url_for("panel"))

    if reunion["estado"] != "Aceptada":
        flash(
            "Solo puedes entrar cuando el tutor haya aceptado la reunión.",
            "aviso"
        )
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=reunion["investigacion_id"]
        ))

    enlace_meet = reunion["enlace_meet"] or ""

    if not enlace_meet.startswith("https://meet.google.com/"):
        flash(
            "El tutor todavía no ha guardado un enlace válido de Google Meet.",
            "aviso"
        )
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=reunion["investigacion_id"]
        ))

    return redirect(enlace_meet)



# ============================================================
# EVALUACIÓN FINAL Y ARCHIVO AUTOMÁTICO DE MONOGRAFÍAS
# ============================================================

@app.route(
    "/investigaciones/<int:investigacion_id>/evaluacion-final",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def evaluacion_final(investigacion_id):

    import os
    import uuid
    from werkzeug.utils import secure_filename
    from flask import current_app

    usuario = usuario_actual()

    archivo = request.files.get("archivo_final")
    nota = request.form.get("nota_final", type=float)

    # --------------------------------------------------------
    # VALIDAR NOTA
    # --------------------------------------------------------

    if nota is None or not 0 <= nota <= 100:
        flash("La nota final debe estar entre 0 y 100.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    # --------------------------------------------------------
    # VALIDAR PDF
    # --------------------------------------------------------

    if not archivo or not archivo.filename:
        flash("Debes adjuntar el PDF completo de la monografía.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    if not archivo.filename.lower().endswith(".pdf"):
        flash("El archivo final debe estar en formato PDF.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    # --------------------------------------------------------
    # PREPARAR CARPETA DE MONOGRAFÍAS
    # --------------------------------------------------------

    carpeta = os.path.join(
        current_app.static_folder,
        "uploads",
        "monografias"
    )

    os.makedirs(carpeta, exist_ok=True)

    nombre_original = secure_filename(archivo.filename)

    if not nombre_original:
        flash("El nombre del archivo no es válido.", "error")
        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))

    nombre_archivo = (
        f"investigacion_{investigacion_id}_"
        f"{uuid.uuid4().hex}_{nombre_original}"
    )

    ruta_completa = os.path.join(carpeta, nombre_archivo)
    ruta_relativa = f"uploads/monografias/{nombre_archivo}"

    archivo_guardado = False

    try:
        with conectar_db() as db:

            # ------------------------------------------------
            # COMPROBAR INVESTIGACIÓN Y PERMISOS
            # ------------------------------------------------

            investigacion = db.execute(
                """
                SELECT *
                FROM investigaciones
                WHERE id = ?
                """,
                (investigacion_id,)
            ).fetchone()

            if not investigacion:
                flash("Investigación no encontrada.", "error")
                return redirect(url_for("panel"))

            if (
                usuario["rol"] == "tutor"
                and investigacion["profesor_id"] != usuario["id"]
            ):
                flash("No tienes permiso para evaluar esta investigación.", "error")
                return redirect(url_for("panel"))

            if investigacion["finalizada"]:
                flash("Esta investigación ya está finalizada.", "error")
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # ------------------------------------------------
            # LOS SEIS NIVELES DEBEN ESTAR APROBADOS
            # ------------------------------------------------

            niveles_aprobados = db.execute(
                """
                SELECT COUNT(*) AS total
                FROM niveles_investigacion
                WHERE investigacion_id = ?
                  AND nivel BETWEEN 1 AND 6
                  AND estado = 'Aprobado'
                """,
                (investigacion_id,)
            ).fetchone()["total"]

            if niveles_aprobados != 6:
                flash(
                    "No se puede finalizar: los seis niveles deben estar aprobados.",
                    "error"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # ------------------------------------------------
            # PREPARAR COLUMNA PARA VINCULAR LA MONOGRAFÍA
            # ------------------------------------------------

            columnas = {
                fila["name"]
                for fila in db.execute(
                    "PRAGMA table_info(recursos_biblioteca)"
                ).fetchall()
            }

            if "investigacion_id" not in columnas:
                db.execute(
                    """
                    ALTER TABLE recursos_biblioteca
                    ADD COLUMN investigacion_id INTEGER
                    """
                )
                columnas.add("investigacion_id")

            # ------------------------------------------------
            # EVITAR ARCHIVAR DOS VECES LA MISMA INVESTIGACIÓN
            # ------------------------------------------------

            existente = db.execute(
                """
                SELECT id
                FROM recursos_biblioteca
                WHERE investigacion_id = ?
                  AND tipo = 'Monografía'
                LIMIT 1
                """,
                (investigacion_id,)
            ).fetchone()

            if existente:
                flash(
                    "Esta investigación ya tiene una monografía archivada.",
                    "error"
                )
                return redirect(url_for(
                    "detalle_investigacion",
                    investigacion_id=investigacion_id
                ))

            # ------------------------------------------------
            # GUARDAR PDF
            # ------------------------------------------------

            archivo.save(ruta_completa)
            archivo_guardado = True

            # ------------------------------------------------
            # REGISTRAR MONOGRAFÍA EN LA BIBLIOTECA
            # ------------------------------------------------

            datos = {
                "titulo": investigacion["titulo"],
                "descripcion": "Monografía final evaluada y aprobada.",
                "tipo": "Monografía",
                "nivel": 6,
                "area_principal": investigacion["area_principal"],
                "subarea": investigacion["subarea"],
                "url": ruta_relativa,
                "archivo": ruta_relativa,
                "gestion": db.execute(
                    "SELECT CAST(strftime('%Y', 'now', 'localtime') AS INTEGER)"
                ).fetchone()[0],
                "creado_por": usuario["id"],
                "creado_en": db.execute(
                    "SELECT CURRENT_TIMESTAMP"
                ).fetchone()[0],
                "investigacion_id": investigacion_id
            }

            # Usar únicamente columnas existentes.
            datos = {
                campo: valor
                for campo, valor in datos.items()
                if campo in columnas
            }

            obligatorias = {"titulo", "tipo", "archivo"}

            if not obligatorias.issubset(datos):
                raise RuntimeError(
                    "Faltan columnas necesarias en recursos_biblioteca."
                )

            campos_sql = ", ".join(
                f'"{campo}"' for campo in datos
            )
            marcadores = ", ".join("?" for _ in datos)

            db.execute(
                f"""
                INSERT INTO recursos_biblioteca ({campos_sql})
                VALUES ({marcadores})
                """,
                tuple(datos.values())
            )

            # ------------------------------------------------
            # FINALIZAR Y REVELAR LA NOTA
            # ------------------------------------------------

            db.execute(
                """
                UPDATE investigaciones
                SET nota_final = ?,
                    nota_visible = 1,
                    finalizada = 1,
                    nivel_actual = 6,
                    estado = 'Finalizada',
                    estado_evaluacion = 'Aprobado'
                WHERE id = ?
                """,
                (nota, investigacion_id)
            )

            # Registrar el evento si la función ya está disponible.
            registrar_evento_progreso_db(
                db,
                investigacion_id,
                6,
                "Monografía final aprobada y archivada"
            )

        flash(
            "¡Evaluación finalizada! La nota se reveló y la monografía fue archivada.",
            "exito"
        )

        return redirect(url_for("biblioteca_monografias"))

    except Exception:
        if archivo_guardado and os.path.isfile(ruta_completa):
            try:
                os.remove(ruta_completa)
            except OSError:
                current_app.logger.exception(
                    "No se pudo limpiar el PDF tras un error."
                )

        current_app.logger.exception(
            "Error al finalizar y archivar la monografía."
        )

        flash(
            "No se pudo finalizar la investigación. Revisa la consola de Flask.",
            "error"
        )

        return redirect(url_for(
            "detalle_investigacion",
            investigacion_id=investigacion_id
        ))


# ============================================================
# RESULTADO FINAL DEL ESTUDIANTE
# ============================================================

@app.route(
    "/resultado"
)
@roles_requeridos("estudiante")
def resultado():

    usuario = usuario_actual()

    investigacion = obtener_investigacion_usuario(
        usuario["id"]
    )


    if not investigacion:

        return render_template(
            "resultado.html",
            investigacion=None,
            disponible=False
        )


    if not investigacion["finalizada"]:

        return render_template(
            "resultado.html",
            investigacion=investigacion,
            disponible=False
        )


    with conectar_db() as db:

        ranking = db.execute(
            """
            SELECT
                i.id,
                i.titulo,
                i.nota_final,
                i.area_principal,
                i.subarea,
                g.nombre AS grupo_nombre,
                t.nombre AS profesor_nombre,
                t.apellido AS profesor_apellido
            FROM investigaciones i
            JOIN grupos g
                ON g.id = i.grupo_id
            LEFT JOIN usuarios t
                ON t.id = i.profesor_id
            WHERE i.finalizada = 1
            AND i.nota_visible = 1
            ORDER BY i.nota_final DESC, i.id ASC
            """
        ).fetchall()


    posicion = None


    for indice, fila in enumerate(
        ranking,
        start=1
    ):

        if fila["id"] == investigacion["id"]:

            posicion = indice

            break


    return render_template(
        "resultado.html",
        investigacion=investigacion,
        disponible=True,
        ranking=ranking,
        posicion=posicion
    )


# ============================================================
# RANKING GENERAL
# ============================================================

@app.route(
    "/ranking"
)
@login_requerido
def ranking():

    with conectar_db() as db:

        lista = db.execute(
            """
            SELECT
                i.id,
                i.titulo,
                i.nota_final,
                i.area_principal,
                i.subarea,
                g.nombre AS grupo_nombre,
                t.nombre AS profesor_nombre,
                t.apellido AS profesor_apellido
            FROM investigaciones i
            JOIN grupos g
                ON g.id = i.grupo_id
            LEFT JOIN usuarios t
                ON t.id = i.profesor_id
            WHERE i.finalizada = 1
            AND i.nota_visible = 1
            ORDER BY i.nota_final DESC, i.id ASC
            """
        ).fetchall()


    return render_template(
        "ranking.html",
        ranking=lista
    )


# ============================================================
# ADMINISTRACIÓN DE USUARIOS
# ============================================================

@app.route(
    "/usuarios",
    methods=["GET", "POST"]
)
@roles_requeridos("admin")
def usuarios():

    if request.method == "POST":

        nombre = request.form.get(
            "nombre",
            ""
        ).strip()

        apellido = request.form.get(
            "apellido",
            ""
        ).strip()

        usuario_nuevo = request.form.get(
            "usuario",
            ""
        ).strip()

        correo = request.form.get(
            "correo",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        rol = request.form.get(
            "rol",
            ""
        )

        curso = request.form.get(
            "curso",
            ""
        ).strip()


        if (
            not nombre
            or not apellido
            or not usuario_nuevo
            or len(password) < 8
            or rol not in (
                "admin",
                "tutor",
                "estudiante"
            )
        ):

            flash(
                "Completa correctamente todos los campos.",
                "error"
            )

        else:

            try:

                with conectar_db() as db:

                    cursor = db.execute(
                        """
                        INSERT INTO usuarios
                        (
                            nombre,
                            apellido,
                            usuario,
                            correo,
                            password_hash,
                            rol,
                            curso
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            nombre,
                            apellido,
                            usuario_nuevo,
                            correo or None,
                            generate_password_hash(
                                password
                            ),
                            rol,
                            curso or None
                        )
                    )


                    nuevo_usuario_id = cursor.lastrowid


                    # Si se crea un profesor con especialidad
                    # desde el formulario, se intenta registrar.
                    especialidad = request.form.get(
                        "especialidad",
                        ""
                    ).strip()


                    if (
                        rol == "tutor"
                        and
                        especialidad
                    ):

                        db.execute(
                            """
                            INSERT OR IGNORE INTO
                            especialidades_tutor
                            (
                                tutor_id,
                                especialidad
                            )
                            VALUES (?, ?)
                            """,
                            (
                                nuevo_usuario_id,
                                especialidad
                            )
                        )


                flash(
                    "Usuario creado correctamente.",
                    "exito"
                )


            except sqlite3.IntegrityError:

                flash(
                    "Ese nombre de usuario o correo ya existe.",
                    "error"
                )


    with conectar_db() as db:

        lista = db.execute(
            """
            SELECT
                id,
                nombre,
                apellido,
                usuario,
                correo,
                rol,
                curso,
                activo,
                creado_en
            FROM usuarios
            ORDER BY rol, apellido, nombre
            """
        ).fetchall()


        catalogo = db.execute(
            """
            SELECT *
            FROM especialidades_catalogo
            ORDER BY nombre
            """
        ).fetchall()


    return render_template(
        "usuarios.html",
        usuarios=lista,
        catalogo=catalogo
    )


# ============================================================
# CAMBIAR ESTADO DE USUARIO
# ============================================================

@app.route(
    "/usuarios/<int:usuario_id>/estado",
    methods=["POST"]
)
@roles_requeridos("admin")
def cambiar_estado_usuario(
    usuario_id
):

    if usuario_id == session.get(
        "usuario_id"
    ):

        flash(
            "No puedes desactivar tu propia cuenta.",
            "error"
        )

        return redirect(
            url_for("usuarios")
        )


    with conectar_db() as db:

        usuario = db.execute(
            """
            SELECT activo
            FROM usuarios
            WHERE id = ?
            """,
            (usuario_id,)
        ).fetchone()


        if usuario:

            nuevo_estado = (
                0
                if usuario["activo"]
                else 1
            )


            db.execute(
                """
                UPDATE usuarios
                SET activo = ?
                WHERE id = ?
                """,
                (
                    nuevo_estado,
                    usuario_id
                )
            )


    return redirect(
        url_for("usuarios")
    )



# ============================================================
# VER NOTIFICACIONES
# ============================================================

@app.route("/notificaciones")
@login_requerido
def notificaciones():
    usuario = usuario_actual()

    with conectar_db() as db:
        asegurar_tabla_notificaciones(db)

        avisos = db.execute(
            """
            SELECT
                n.*,
                i.titulo AS investigacion_titulo
            FROM notificaciones n
            LEFT JOIN investigaciones i
                ON i.id = n.investigacion_id
            WHERE n.usuario_id = ?
            ORDER BY
                n.leida ASC,
                n.creado_en DESC,
                n.id DESC
            """,
            (usuario["id"],)
        ).fetchall()

    return render_template(
        "notificaciones.html",
        avisos=avisos
    )


# ============================================================
# CONTADOR GLOBAL DE NOTIFICACIONES
# ============================================================

@app.context_processor
def datos_notificaciones():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return {"notificaciones_no_leidas": 0}

    try:
        with conectar_db() as db:
            asegurar_tabla_notificaciones(db)

            fila = db.execute(
                """
                SELECT COUNT(*) AS total
                FROM notificaciones
                WHERE usuario_id = ?
                  AND leida = 0
                """,
                (usuario_id,)
            ).fetchone()

        return {
            "notificaciones_no_leidas": fila["total"]
        }

    except sqlite3.Error:
        app.logger.exception(
            "Error al consultar las notificaciones"
        )

        return {"notificaciones_no_leidas": 0}



# ============================================================
# MARCAR NOTIFICACIÓN COMO LEÍDA
# ============================================================

@app.route(
    "/notificaciones/<int:notificacion_id>/leer",
    methods=["POST"]
)
@login_requerido
def marcar_notificacion_leida(notificacion_id):
    usuario = usuario_actual()

    with conectar_db() as db:
        asegurar_tabla_notificaciones(db)

        db.execute(
            """
            UPDATE notificaciones
            SET leida = 1
            WHERE id = ?
              AND usuario_id = ?
            """,
            (notificacion_id, usuario["id"])
        )

    flash("Notificación marcada como leída.", "exito")
    return redirect(url_for("notificaciones"))


# ============================================================
# CONTADOR GLOBAL DE NOTIFICACIONES
# ============================================================

@app.context_processor
def datos_notificaciones():
    usuario_id = session.get("usuario_id")

    if not usuario_id:
        return {"notificaciones_no_leidas": 0}

    try:
        with conectar_db() as db:
            asegurar_tabla_notificaciones(db)

            fila = db.execute(
                """
                SELECT COUNT(*) AS total
                FROM notificaciones
                WHERE usuario_id = ?
                  AND leida = 0
                """,
                (usuario_id,)
            ).fetchone()

        return {
            "notificaciones_no_leidas": fila["total"]
        }

    except sqlite3.Error:
        app.logger.exception(
            "Error al consultar las notificaciones"
        )
        return {"notificaciones_no_leidas": 0}



# ============================================================
# CRONOGRAMA GENERAL
# ============================================================

@app.route("/cronograma")
@login_requerido
def cronograma():

    usuario = usuario_actual()

    # Fechas oficiales de la gestión 2026.
    # Son visibles para todos los usuarios.
    with conectar_db() as db:
        eventos_cronograma = db.execute(
            """
            SELECT *
            FROM eventos_cronograma
            WHERE activa = 1
            ORDER BY fecha, hora_inicio, id
            """
        ).fetchall()

    # --------------------------------------------------------
    # ESTUDIANTE
    # --------------------------------------------------------
    if usuario["rol"] == "estudiante":

        investigacion = obtener_investigacion_usuario(
            usuario["id"]
        )

        # Mostrar el cronograma institucional aunque no tenga
        # una investigación asignada.
        if not investigacion:
            return render_template(
                "cronograma.html",
                tareas=[],
                niveles=NIVELES,
                eventos_cronograma=eventos_cronograma
            )

        with conectar_db() as db:
            tareas = db.execute(
                """
                SELECT *
                FROM tareas
                WHERE investigacion_id = ?
                ORDER BY fecha_limite, id
                """,
                (investigacion["id"],)
            ).fetchall()

        return render_template(
            "cronograma.html",
            tareas=tareas,
            niveles=NIVELES,
            eventos_cronograma=eventos_cronograma
        )

    # --------------------------------------------------------
    # TUTOR
    # --------------------------------------------------------
    if usuario["rol"] == "tutor":

        with conectar_db() as db:
            tareas = db.execute(
                """
                SELECT
                    ta.*,
                    i.titulo
                FROM tareas ta
                JOIN investigaciones i
                    ON i.id = ta.investigacion_id
                WHERE i.profesor_id = ?
                ORDER BY ta.fecha_limite, ta.id
                """,
                (usuario["id"],)
            ).fetchall()

        return render_template(
            "cronograma.html",
            tareas=tareas,
            niveles=NIVELES,
            eventos_cronograma=eventos_cronograma
        )

    # --------------------------------------------------------
    # ADMINISTRADOR
    # --------------------------------------------------------
    with conectar_db() as db:
        tareas = db.execute(
            """
            SELECT
                ta.*,
                i.titulo
            FROM tareas ta
            JOIN investigaciones i
                ON i.id = ta.investigacion_id
            ORDER BY ta.fecha_limite, ta.id
            """
        ).fetchall()

    return render_template(
        "cronograma.html",
        tareas=tareas,
        niveles=NIVELES,
        eventos_cronograma=eventos_cronograma
    )



# ============================================================
# ARCHIVOS SUBIDOS
# ============================================================

@app.route(
    "/uploads/<path:nombre>"
)
@login_requerido
def descargar_archivo(
    nombre
):

    # Evita aceptar rutas absolutas o manipuladas.
    nombre_seguro = secure_filename(
        Path(nombre).name
    )

    if not nombre_seguro:

        flash(
            "Archivo no válido.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    ruta = UPLOAD_DIR / nombre_seguro


    if not ruta.exists():

        flash(
            "El archivo no existe.",
            "error"
        )

        return redirect(
            url_for("panel")
        )


    return send_from_directory(
        UPLOAD_DIR,
        nombre_seguro
    )


# ============================================================
# API SIMPLE PARA ACTUALIZAR CHAT
# ============================================================

@app.route(
    "/api/interacciones/<int:investigacion_id>"
)
@login_requerido
def api_interacciones(
    investigacion_id
):

    usuario = usuario_actual()


    permitido = (
        usuario["rol"] == "admin"
        or
        (
            usuario["rol"] == "tutor"
            and
            profesor_puede_ver(
                investigacion_id,
                usuario["id"]
            )
        )
        or
        (
            usuario["rol"] == "estudiante"
            and
            es_miembro_investigacion(
                usuario["id"],
                investigacion_id
            )
        )
    )


    if not permitido:

        return jsonify(
            {
                "error": "No autorizado"
            }
        ), 403


    with conectar_db() as db:

        mensajes = db.execute(
            """
            SELECT
                m.id,
                m.mensaje,
                m.creado_en,
                u.nombre,
                u.apellido,
                u.rol
            FROM mensajes_chat m
            JOIN usuarios u
                ON u.id = m.autor_id
            WHERE m.investigacion_id = ?
            ORDER BY m.creado_en
            """,
            (investigacion_id,)
        ).fetchall()


    return jsonify(
        [
            dict(mensaje)
            for mensaje in mensajes
        ]
    )


# ============================================================
# MANEJO DE ERRORES
# ============================================================

@app.errorhandler(404)
def error_404(error):
    return render_template(
        "error.html",
        codigo=404,
        mensaje="La página que buscas no existe o ha sido movida."
    ), 404

@app.errorhandler(413)
def error_413(error):

    flash(
        "El archivo supera el límite permitido de 30 MB.",
        "error"
    )

    return redirect(
        request.referrer
        or
        url_for("panel")
    )


@app.errorhandler(500)
def error_500(error):
    return render_template(
        "error.html",
        codigo=500,
        mensaje="Ocurrió un error interno en el servidor."
    ), 500



# ============================================================
# MIGRACIÓN — AGENDA Y SEGUIMIENTO DE TUTORÍAS
# ============================================================

with conectar_db() as db:

    tabla_existe = db.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'solicitudes_reunion'
    """).fetchone()

    if tabla_existe is None:

        print("AVISO: La tabla solicitudes_reunion todavía no existe.")

    else:

        columnas = [
            columna["name"]
            for columna in db.execute(
                "PRAGMA table_info(solicitudes_reunion)"
            ).fetchall()
        ]

        nuevas_columnas = {
            "enlace_meet": "TEXT",
            "acuerdos": "TEXT",
            "compromisos": "TEXT",
            "fecha_realizada": "TEXT"
        }

        for nombre, tipo in nuevas_columnas.items():

            if nombre not in columnas:

                db.execute(f"""
                    ALTER TABLE solicitudes_reunion
                    ADD COLUMN {nombre} {tipo}
                """)

                print(f"OK: columna {nombre} creada.")

            else:

                print(f"OK: columna {nombre} ya existe.")

# ============================================================
# FIN DE LA MIGRACIÓN
# ============================================================


# ============================================================
# CARGA DE TUTORES — ADMINISTRADOR
# ============================================================

@app.route("/admin/carga-tutores", methods=["GET", "POST"])
@login_requerido
@roles_requeridos("admin")
def admin_carga_tutores():

    # ========================================================
    # ASIGNAR TUTOR A UN GRUPO
    # ========================================================

    if request.method == "POST":

        investigacion_id = request.form.get(
            "investigacion_id", type=int
        )

        tutor_id = request.form.get(
            "tutor_id", type=int
        )

        if not investigacion_id or not tutor_id:
            flash("Selecciona un grupo y un tutor.", "error")
            return redirect(url_for("admin_carga_tutores"))

        with conectar_db() as db:

            tutor = db.execute("""
                SELECT id
                FROM usuarios
                WHERE id = ?
                  AND rol = 'tutor'
                  AND activo = 1
            """, (tutor_id,)).fetchone()

            if not tutor:
                flash("El tutor seleccionado no es válido.", "error")
                return redirect(url_for("admin_carga_tutores"))

            investigacion = db.execute("""
                SELECT
                    i.id,
                    i.grupo_id,
                    i.profesor_id,
                    g.nombre AS grupo_nombre
                FROM investigaciones i
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.id = ?
                  AND COALESCE(i.finalizada, 0) = 0
            """, (investigacion_id,)).fetchone()

            if not investigacion:
                flash(
                    "El grupo seleccionado no existe o ya está finalizado.",
                    "error"
                )
                return redirect(url_for("admin_carga_tutores"))

            if investigacion["profesor_id"] is not None:
                flash(
                    "Este grupo ya tiene un tutor asignado.",
                    "error"
                )
                return redirect(url_for("admin_carga_tutores"))

            db.execute("""
                UPDATE investigaciones
                SET profesor_id = ?
                WHERE id = ?
                  AND profesor_id IS NULL
            """, (tutor_id, investigacion_id))

        flash(
            f"El grupo {investigacion['grupo_nombre']} fue asignado correctamente.",
            "exito"
        )

        return redirect(url_for("admin_carga_tutores"))

    # ========================================================
    # CONSULTAR TUTORES Y SU CARGA DE TRABAJO
    # ========================================================

    with conectar_db() as db:

        tutores = db.execute("""
            SELECT
                u.id,
                u.nombre,
                u.apellido,

                COUNT(DISTINCT
                    CASE
                        WHEN COALESCE(i.finalizada, 0) = 0
                        THEN i.grupo_id
                    END
                ) AS grupos_activos,

                COUNT(DISTINCT i.grupo_id) AS grupos_totales

            FROM usuarios u

            LEFT JOIN investigaciones i
                ON i.profesor_id = u.id

            WHERE u.rol = 'tutor'
              AND u.activo = 1

            GROUP BY
                u.id,
                u.nombre,
                u.apellido

            ORDER BY
                grupos_activos ASC,
                grupos_totales ASC,
                u.apellido ASC,
                u.nombre ASC
        """).fetchall()

        # ====================================================
        # SUGERENCIA DEL TUTOR CON MENOS GRUPOS ACTIVOS
        # ====================================================

        tutor_sugerido = tutores[0] if tutores else None

        # ====================================================
        # GRUPOS CON INVESTIGACIÓN SIN TUTOR
        # ====================================================

        grupos_sin_tutor = db.execute("""
            SELECT
                i.id AS investigacion_id,
                i.grupo_id,
                i.titulo,
                g.nombre AS grupo_nombre

            FROM investigaciones i

            JOIN grupos g
                ON g.id = i.grupo_id

            WHERE i.profesor_id IS NULL
              AND COALESCE(i.finalizada, 0) = 0

            ORDER BY
                g.creado_en DESC
        """).fetchall()

    return render_template(
        "carga_tutores.html",
        usuario=usuario_actual(),
        tutores=tutores,
        tutor_sugerido=tutor_sugerido,
        grupos_sin_tutor=grupos_sin_tutor
    )


# ============================================================
# REUNIONES PROGRAMADAS DIRECTAMENTE POR EL TUTOR
# ============================================================

with conectar_db() as db:

    db.execute("""
        CREATE TABLE IF NOT EXISTS reuniones_tutor_programadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            tutor_id INTEGER NOT NULL,
            motivo TEXT NOT NULL,
            fecha_solicitada TEXT NOT NULL,
            hora_solicitada TEXT NOT NULL,
            duracion INTEGER NOT NULL DEFAULT 30,
            enlace_meet TEXT,
            acuerdos TEXT,
            compromisos TEXT,
            fecha_realizada TEXT,
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (investigacion_id)
                REFERENCES investigaciones(id)
                ON DELETE CASCADE,

            FOREIGN KEY (tutor_id)
                REFERENCES usuarios(id)
                ON DELETE CASCADE
        )
    """)

# ============================================================
# FIN DE LA TABLA
# ============================================================


# ============================================================
# AGENDA DE TUTORÍAS — PANEL DEL TUTOR
# ============================================================

@app.route("/agenda-tutorias")
@roles_requeridos("tutor")
def agenda_tutorias():

    usuario = usuario_actual()

    with conectar_db() as db:

        fecha_hoy = db.execute("""
            SELECT date('now', 'localtime')
        """).fetchone()[0]

        # ----------------------------------------------------
        # SOLICITUDES ENVIADAS POR LOS ESTUDIANTES
        # ----------------------------------------------------

        solicitudes = db.execute("""
            SELECT
                sr.*,
                i.titulo AS investigacion_titulo,
                g.nombre AS grupo_nombre,
                TRIM(
                    u.nombre || ' ' || COALESCE(u.apellido, '')
                ) AS estudiante_nombre

            FROM solicitudes_reunion sr

            JOIN investigaciones i
                ON i.id = sr.investigacion_id

            LEFT JOIN grupos g
                ON g.id = i.grupo_id

            LEFT JOIN usuarios u
                ON u.id = sr.estudiante_id

            WHERE i.profesor_id = ?
              AND sr.estado = 'Pendiente'

            ORDER BY sr.fecha_creado DESC
        """, (usuario["id"],)).fetchall()

        # ----------------------------------------------------
        # REUNIONES ACEPTADAS SOLICITADAS POR ESTUDIANTES
        # ----------------------------------------------------

        reuniones = db.execute("""
            SELECT
                sr.*,
                i.titulo AS investigacion_titulo,
                g.nombre AS grupo_nombre,
                TRIM(
                    u.nombre || ' ' || COALESCE(u.apellido, '')
                ) AS estudiante_nombre

            FROM solicitudes_reunion sr

            JOIN investigaciones i
                ON i.id = sr.investigacion_id

            LEFT JOIN grupos g
                ON g.id = i.grupo_id

            LEFT JOIN usuarios u
                ON u.id = sr.estudiante_id

            WHERE i.profesor_id = ?
              AND sr.estado = 'Aceptada'

            ORDER BY sr.fecha_solicitada, sr.hora_solicitada
        """, (usuario["id"],)).fetchall()

        # ----------------------------------------------------
        # REUNIONES PROGRAMADAS DIRECTAMENTE POR EL TUTOR
        # ----------------------------------------------------

        reuniones_directas = db.execute("""
            SELECT
                rp.*,
                i.titulo AS investigacion_titulo,
                g.nombre AS grupo_nombre,
                'Programada por tutor' AS estudiante_nombre

            FROM reuniones_tutor_programadas rp

            JOIN investigaciones i
                ON i.id = rp.investigacion_id

            LEFT JOIN grupos g
                ON g.id = i.grupo_id

            WHERE rp.tutor_id = ?

            ORDER BY rp.fecha_solicitada, rp.hora_solicitada
        """, (usuario["id"],)).fetchall()

        # ----------------------------------------------------
        # INVESTIGACIONES DISPONIBLES PARA PROGRAMAR
        # ----------------------------------------------------

        investigaciones_tutor = db.execute("""
            SELECT
                i.id,
                i.titulo,
                g.nombre AS grupo_nombre

            FROM investigaciones i

            LEFT JOIN grupos g
                ON g.id = i.grupo_id

            WHERE i.profesor_id = ?

            ORDER BY g.nombre, i.titulo
        """, (usuario["id"],)).fetchall()

    # --------------------------------------------------------
    # ORGANIZAR REUNIONES
    # --------------------------------------------------------

    proximas = []
    pendientes = []
    realizadas = []

    todas_reuniones = []

    for reunion in reuniones:
        dato = dict(reunion)
        dato["origen"] = "solicitud"
        todas_reuniones.append(dato)

    for reunion in reuniones_directas:
        dato = dict(reunion)
        dato["origen"] = "programada"
        todas_reuniones.append(dato)

    for reunion in todas_reuniones:

        if reunion.get("fecha_realizada"):

            realizadas.append(reunion)

        elif reunion["fecha_solicitada"] >= fecha_hoy:

            proximas.append(reunion)

        else:

            pendientes.append(reunion)

    proximas.sort(
        key=lambda r: (
            r["fecha_solicitada"],
            r["hora_solicitada"]
        )
    )

    pendientes.sort(
        key=lambda r: (
            r["fecha_solicitada"],
            r["hora_solicitada"]
        )
    )

    realizadas.sort(
        key=lambda r: r.get("fecha_realizada") or "",
        reverse=True
    )

    return render_template(
        "agenda_tutorias.html",
        usuario=usuario,
        proximas=proximas,
        pendientes=pendientes,
        realizadas=realizadas,
        solicitudes=solicitudes,
        investigaciones_tutor=investigaciones_tutor
    )


# ============================================================
# REGISTRAR UNA TUTORÍA REALIZADA
# ============================================================

@app.route(
    "/reuniones/<int:reunion_id>/finalizar",
    methods=["POST"]
)
@roles_requeridos("tutor")
def finalizar_tutoria(reunion_id):

    usuario = usuario_actual()

    acuerdos = request.form.get("acuerdos", "").strip()
    compromisos = request.form.get("compromisos", "").strip()

    if not acuerdos or not compromisos:

        flash(
            "Completá los acuerdos y compromisos antes de finalizar.",
            "warning"
        )

        return redirect(url_for("agenda_tutorias"))

    with conectar_db() as db:

        reunion = db.execute("""
            SELECT
                sr.id,
                sr.estado,
                i.profesor_id
            FROM solicitudes_reunion sr
            JOIN investigaciones i
                ON i.id = sr.investigacion_id
            WHERE sr.id = ?
        """, (reunion_id,)).fetchone()

        if not reunion:

            flash("No se encontró la reunión.", "danger")
            return redirect(url_for("agenda_tutorias"))

        if reunion["profesor_id"] != usuario["id"]:

            flash("No tenés permiso para modificar esta reunión.", "danger")
            return redirect(url_for("agenda_tutorias"))

        if reunion["estado"] != "Aceptada":

            flash("Solo podés finalizar reuniones aceptadas.", "warning")
            return redirect(url_for("agenda_tutorias"))

        db.execute("""
            UPDATE solicitudes_reunion
            SET
                acuerdos = ?,
                compromisos = ?,
                fecha_realizada = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (acuerdos, compromisos, reunion_id))

    flash("Tutoría registrada correctamente.", "success")

    return redirect(url_for("agenda_tutorias"))

# ============================================================
# FIN DE LA AGENDA DE TUTORÍAS
# ============================================================

# ============================================================
# PROGRAMAR REUNIÓN DIRECTAMENTE COMO TUTOR
# ============================================================

@app.route("/agenda-tutorias/programar", methods=["POST"])
@roles_requeridos("tutor")
def programar_tutoria():

    usuario = usuario_actual()

    investigacion_id = request.form.get(
        "investigacion_id", type=int
    )

    motivo = request.form.get("motivo", "").strip()
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    duracion = request.form.get("duracion", type=int) or 30
    enlace_meet = request.form.get("enlace_meet", "").strip()

    if not investigacion_id or not motivo or not fecha or not hora:
        flash("Completá el grupo, motivo, fecha y hora.", "warning")
        return redirect(url_for("agenda_tutorias"))

    if duracion not in (15, 30, 45, 60):
        duracion = 30

    if enlace_meet and not enlace_meet.startswith(
        "https://meet.google.com/"
    ):
        flash("Ingresá un enlace válido de Google Meet.", "warning")
        return redirect(url_for("agenda_tutorias"))

    with conectar_db() as db:

        investigacion = db.execute("""
            SELECT id, titulo
            FROM investigaciones
            WHERE id = ?
              AND profesor_id = ?
        """, (investigacion_id, usuario["id"])).fetchone()

        if not investigacion:
            flash("No se encontró una investigación asignada a tu cuenta.", "danger")
            return redirect(url_for("agenda_tutorias"))

        db.execute("""
            INSERT INTO reuniones_tutor_programadas (
                investigacion_id,
                tutor_id,
                motivo,
                fecha_solicitada,
                hora_solicitada,
                duracion,
                enlace_meet
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            investigacion_id,
            usuario["id"],
            motivo,
            fecha,
            hora,
            duracion,
            enlace_meet or None
        ))

    flash("La reunión fue programada correctamente.", "success")

    return redirect(url_for("agenda_tutorias"))

# ============================================================
# FIN DE PROGRAMACIÓN DIRECTA
# ============================================================

# ============================================================
# TESIS LAB — PAQUETE DE INNOVACIONES (30 FUNCIONES)
# Extensión compatible: conserva las tablas y rutas existentes.
# ============================================================

from flask import render_template_string, make_response
from datetime import timedelta
import csv
import io
import zipfile
import difflib
import re
import json
import hashlib


def profesor_puede_ver(investigacion_id, profesor_id):
    """Comprueba que el tutor sea el asignado a la investigación."""
    with conectar_db() as db:
        fila = db.execute(
            "SELECT 1 FROM investigaciones WHERE id=? AND profesor_id=?",
            (investigacion_id, profesor_id)
        ).fetchone()
    return fila is not None


def asegurar_innovaciones():
    """Migración aditiva. No elimina ni reemplaza tablas existentes."""
    with conectar_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS observaciones_puntos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            historial_id INTEGER,
            texto TEXT NOT NULL,
            corregida INTEGER NOT NULL DEFAULT 0,
            creada_por INTEGER,
            corregida_por INTEGER,
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            corregida_en TEXT,
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY(historial_id) REFERENCES historial_entregas(id) ON DELETE SET NULL,
            FOREIGN KEY(creada_por) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY(corregida_por) REFERENCES usuarios(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS tareas_grupo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            responsable_id INTEGER,
            fecha_limite TEXT,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            creada_por INTEGER NOT NULL,
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completada_en TEXT,
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY(responsable_id) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY(creada_por) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS eventos_cronograma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            fecha TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fin TEXT,
            tipo TEXT NOT NULL DEFAULT 'Hito',
            activa INTEGER NOT NULL DEFAULT 1,
            creada_por INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            modificada_en TEXT,
            FOREIGN KEY (creada_por)
                REFERENCES usuarios(id) ON DELETE SET NULL,
            UNIQUE (titulo, fecha)
        );

        CREATE INDEX IF NOT EXISTS idx_eventos_cronograma_fecha
        ON eventos_cronograma (fecha, hora_inicio);

        CREATE TABLE IF NOT EXISTS checklist_academico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            apartado TEXT NOT NULL,
            cumplido INTEGER NOT NULL DEFAULT 0,
            actualizado_por INTEGER,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(investigacion_id, apartado),
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY(actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS criterios_rubrica (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            criterio TEXT NOT NULL,
            puntaje_maximo REAL NOT NULL DEFAULT 20,
            UNIQUE(investigacion_id, nivel, criterio),
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notas_rubrica_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criterio_id INTEGER NOT NULL,
            evaluador_id INTEGER NOT NULL,
            puntaje REAL NOT NULL,
            comentario TEXT,
            evaluado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(criterio_id) REFERENCES criterios_rubrica(id) ON DELETE CASCADE,
            FOREIGN KEY(evaluador_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS compromisos_reunion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reunion_id INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            responsable_id INTEGER,
            fecha_limite TEXT,
            cumplido INTEGER NOT NULL DEFAULT 0,
            creado_por INTEGER NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(reunion_id) REFERENCES solicitudes_reunion(id) ON DELETE CASCADE,
            FOREIGN KEY(responsable_id) REFERENCES usuarios(id) ON DELETE SET NULL,
            FOREIGN KEY(creado_por) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comunicados_institucionales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            destinatario TEXT NOT NULL DEFAULT 'todos',
            curso TEXT,
            publicado_por INTEGER NOT NULL,
            publicado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            activo INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(publicado_por) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS lecturas_comunicados (
            comunicado_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL,
            leido_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(comunicado_id, usuario_id),
            FOREIGN KEY(comunicado_id) REFERENCES comunicados_institucionales(id) ON DELETE CASCADE,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS auditoria_tesislab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            accion TEXT NOT NULL,
            entidad TEXT NOT NULL,
            entidad_id INTEGER,
            detalle TEXT,
            ip TEXT,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS logros_academicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            investigacion_id INTEGER,
            codigo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            descripcion TEXT,
            obtenido_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(usuario_id, investigacion_id, codigo),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS mapa_conocimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investigacion_id INTEGER NOT NULL,
            elemento TEXT NOT NULL,
            contenido TEXT NOT NULL,
            actualizado_por INTEGER,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(investigacion_id, elemento),
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY(actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS feria_digital (
            investigacion_id INTEGER PRIMARY KEY,
            resumen TEXT NOT NULL,
            resultado TEXT,
            autorizada INTEGER NOT NULL DEFAULT 0,
            destacada INTEGER NOT NULL DEFAULT 0,
            publicada_por INTEGER,
            publicada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(investigacion_id) REFERENCES investigaciones(id) ON DELETE CASCADE,
            FOREIGN KEY(publicada_por) REFERENCES usuarios(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tareas_grupo_investigacion ON tareas_grupo(investigacion_id, estado, fecha_limite);
        CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria_tesislab(creado_en);
        CREATE INDEX IF NOT EXISTS idx_observaciones ON observaciones_puntos(investigacion_id, nivel, corregida);
        """)

        # Agregar columnas de seguridad sin eliminar datos existentes.
        columnas = {
            fila["name"]
            for fila in db.execute(
                "PRAGMA table_info(auditoria_tesislab)"
            ).fetchall()
        }

        if "hash_anterior" not in columnas:

            db.execute("""
                ALTER TABLE auditoria_tesislab
                ADD COLUMN hash_anterior TEXT
            """)

        if "hash_actual" not in columnas:

            db.execute("""
                ALTER TABLE auditoria_tesislab
                ADD COLUMN hash_actual TEXT
            """)

        # Inicializar apartados para investigaciones ya creadas.


# ============================================================
# SISTEMA DE AUDITORÍA Y SEGURIDAD SHA-256
# ============================================================

def calcular_hash_auditoria(registro):

    datos = {
        "id": registro["id"],
        "usuario_id": registro["usuario_id"],
        "accion": registro["accion"],
        "entidad": registro["entidad"],
        "entidad_id": registro["entidad_id"],
        "detalle": registro["detalle"],
        "ip": registro["ip"],
        "creado_en": registro["creado_en"],
        "hash_anterior": registro["hash_anterior"]
    }

    contenido = json.dumps(
        datos,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def auditar(
    db,
    accion,
    entidad,
    entidad_id=None,
    detalle=""
):

    usuario_id = session.get("usuario_id")

    ip = request.headers.get(
        "X-Forwarded-For",
        request.remote_addr
    )

    # Obtener el último registro sellado.
    anterior = db.execute("""
        SELECT hash_actual
        FROM auditoria_tesislab
        WHERE hash_actual IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    hash_anterior = (
        anterior["hash_actual"]
        if anterior
        else "GENESIS"
    )

    # Crear el registro.
    cursor = db.execute("""
        INSERT INTO auditoria_tesislab (
            usuario_id,
            accion,
            entidad,
            entidad_id,
            detalle,
            ip,
            hash_anterior
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        usuario_id,
        str(accion)[:100],
        str(entidad)[:80],
        entidad_id,
        str(detalle)[:2000],
        ip,
        hash_anterior
    ))

    # Recuperar el registro creado.
    registro = db.execute("""
        SELECT *
        FROM auditoria_tesislab
        WHERE id = ?
    """, (cursor.lastrowid,)).fetchone()

    # Calcular su sello.
    hash_actual = calcular_hash_auditoria(registro)

    # Guardar el sello.
    db.execute("""
        UPDATE auditoria_tesislab
        SET hash_actual = ?
        WHERE id = ?
    """, (
        hash_actual,
        cursor.lastrowid
    ))


def verificar_integridad_auditoria():

    with conectar_db() as db:

        registros = db.execute("""
            SELECT *
            FROM auditoria_tesislab
            ORDER BY id ASC
        """).fetchall()

    hash_anterior_esperado = "GENESIS"

    total_verificados = 0
    registros_antiguos = 0
    alteraciones = []

    cadena_iniciada = False

    for registro in registros:

        # Los registros históricos sin sello se conservan.
        if not registro["hash_actual"]:

            registros_antiguos += 1

            # Si aparecen después de iniciar la cadena,
            # existe una interrupción sospechosa.
            if cadena_iniciada:

                alteraciones.append({
                    "id": registro["id"],
                    "motivo": "Se encontró un registro sin sello dentro de la cadena."
                })

            continue

        cadena_iniciada = True

        # Comprobar conexión con el registro anterior.
        if registro["hash_anterior"] != hash_anterior_esperado:

            alteraciones.append({
                "id": registro["id"],
                "motivo": "La conexión con el registro anterior no coincide."
            })

        # Volver a calcular el sello.
        hash_calculado = calcular_hash_auditoria(registro)

        if hash_calculado != registro["hash_actual"]:

            alteraciones.append({
                "id": registro["id"],
                "motivo": "El sello SHA-256 fue alterado."
            })

        hash_anterior_esperado = registro["hash_actual"]

        total_verificados += 1

    return {
        "integro": len(alteraciones) == 0,
        "total_verificados": total_verificados,
        "registros_antiguos": registros_antiguos,
        "alteraciones": alteraciones
    }

def auditar(
    db,
    accion,
    entidad,
    entidad_id=None,
    detalle=""
):

    usuario_id = session.get("usuario_id")

    ip = request.headers.get(
        "X-Forwarded-For",
        request.remote_addr
    )

    # Obtener el último sello válido registrado.
    anterior = db.execute("""
        SELECT hash_actual
        FROM auditoria_tesislab
        WHERE hash_actual IS NOT NULL
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()

    hash_anterior = (
        anterior["hash_actual"]
        if anterior
        else "GENESIS"
    )

    # Insertar el nuevo registro.
    cursor = db.execute("""
        INSERT INTO auditoria_tesislab (
            usuario_id,
            accion,
            entidad,
            entidad_id,
            detalle,
            ip,
            hash_anterior
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        usuario_id,
        accion[:100],
        entidad[:80],
        entidad_id,
        detalle[:2000],
        ip,
        hash_anterior
    ))

    # Recuperar el registro recién creado.
    registro = db.execute("""
        SELECT *
        FROM auditoria_tesislab
        WHERE id = ?
    """, (cursor.lastrowid,)).fetchone()

    # Calcular su sello SHA-256.
    hash_actual = calcular_hash_auditoria(registro)

    # Guardar el sello.
    db.execute("""
        UPDATE auditoria_tesislab
        SET hash_actual = ?
        WHERE id = ?
    """, (
        hash_actual,
        cursor.lastrowid
    ))

def verificar_integridad_auditoria():

    with conectar_db() as db:

        registros = db.execute("""
            SELECT *
            FROM auditoria_tesislab
            ORDER BY id ASC
        """).fetchall()

    hash_anterior_esperado = "GENESIS"

    total_verificados = 0
    registros_antiguos = 0
    alteraciones = []

    for registro in registros:

        # Los registros anteriores a la implementación
        # no tienen sellos y se conservan sin modificarlos.
        if not registro["hash_actual"]:

            registros_antiguos += 1

            # No podemos garantizar la integridad de una
            # cadena histórica que todavía no tenía sellos.
            hash_anterior_esperado = "GENESIS"

            continue

        # Comprobar conexión con el registro anterior.
        if registro["hash_anterior"] != hash_anterior_esperado:

            alteraciones.append({
                "id": registro["id"],
                "motivo": "La conexión con el registro anterior no coincide."
            })

        # Volver a calcular el sello del registro.
        hash_calculado = calcular_hash_auditoria(registro)

        if hash_calculado != registro["hash_actual"]:

            alteraciones.append({
                "id": registro["id"],
                "motivo": "El sello SHA-256 fue alterado."
            })

        # El siguiente registro debe apuntar al sello
        # que realmente está almacenado en este registro.
        hash_anterior_esperado = registro["hash_actual"]

        total_verificados += 1

    return {
        "integro": len(alteraciones) == 0,
        "total_verificados": total_verificados,
        "registros_antiguos": registros_antiguos,
        "alteraciones": alteraciones
    }


def _clave_checklist(apartado):
    return "apartado_" + hashlib.sha1(apartado.encode("utf-8")).hexdigest()[:12]


def exigir_acceso_investigacion(usuario, investigacion_id):
    return usuario_puede_ver_investigacion(usuario, investigacion_id)



def html_innovacion(titulo, contenido, subtitulo="TESIS LAB · Centro de innovación"):
    return render_template_string('''
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <title>{{ titulo }} · TESIS LAB</title>

        <style>
            :root {
                --azul: #10264b;
                --azul2: #174a85;
                --fondo: #f4f7fb;
                --borde: #e1e7f0;
                --texto: #18263b;
                --muted: #64748b;
            }

            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                background: var(--fondo);
                font-family: Arial, sans-serif;
                color: var(--texto);
            }

            /* ENCABEZADO */

            header {
                background: var(--azul);
                color: white;
                padding: 20px max(20px, calc((100% - 1120px) / 2));
            }

            header a {
                color: #dbeafe;
                text-decoration: none;
                margin-right: 16px;
                font-size: 14px;
            }

            header a:hover {
                color: white;
            }

            /* CONTENIDO PRINCIPAL */

            main {
                width: 100%;
                max-width: 950px;
                margin: 28px auto;
                padding: 0 18px 40px;
            }

            h1 {
                margin: 0 0 8px;
                font-size: 26px;
                color: var(--azul);
            }

            h2 {
                font-size: 18px;
                margin-top: 0;
            }

            p {
                line-height: 1.5;
            }

            .muted {
                color: var(--muted);
            }

            /* TARJETAS VERTICALES */

            .card {
                display: block;
                width: 100%;
                background: white;
                border: 1px solid var(--borde);
                border-radius: 14px;
                padding: 20px;
                margin: 16px 0;
                box-shadow: 0 3px 12px #14294a0a;
            }

            .grid {
                display: flex;
                flex-direction: column;
                gap: 14px;
            }

            /* BOTONES */

            a.btn,
            button {
                display: inline-block;
                background: var(--azul2);
                color: white;
                border: 0;
                border-radius: 8px;
                padding: 10px 14px;
                text-decoration: none;
                cursor: pointer;
                font-size: 14px;
            }

            a.btn:hover,
            button:hover {
                background: var(--azul);
            }

            a.secondary {
                background: #eaf0f8;
                color: var(--azul);
            }

            /* FORMULARIOS */

            input,
            select,
            textarea {
                width: 100%;
                padding: 10px;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                margin: 6px 0 12px;
                font: inherit;
            }

            textarea {
                min-height: 100px;
                resize: vertical;
            }

            label {
                font-size: 14px;
                font-weight: 600;
            }

            /* TABLAS */

            table {
                width: 100%;
                border-collapse: collapse;
            }

            td,
            th {
                text-align: left;
                padding: 10px;
                border-bottom: 1px solid var(--borde);
                font-size: 14px;
            }

            th {
                color: var(--muted);
            }

            /* ESTADOS */

            .pill {
                display: inline-block;
                padding: 4px 9px;
                border-radius: 20px;
                background: #edf2f7;
                font-size: 12px;
            }

            .verde {
                background: #dcfce7;
                color: #166534;
            }

            .amarillo {
                background: #fef3c7;
                color: #92400e;
            }

            .rojo {
                background: #fee2e2;
                color: #991b1b;
            }

            .barra {
                height: 10px;
                background: #e5e7eb;
                border-radius: 20px;
                overflow: hidden;
            }

            .barra span {
                display: block;
                height: 100%;
                background: #2563eb;
            }

            .flash {
                padding: 10px;
                background: #fff7ed;
                border-radius: 8px;
                margin: 10px 0;
            }

            /* MÓVILES */

            @media (max-width: 600px) {
                header {
                    padding: 18px;
                }

                header a {
                    display: inline-block;
                    margin: 8px 10px 4px 0;
                }

                main {
                    margin-top: 20px;
                    padding: 0 12px 30px;
                }

                h1 {
                    font-size: 22px;
                }

                .card {
                    padding: 15px;
                }

                table {
                    display: block;
                    overflow-x: auto;
                }
            }
        </style>
    </head>

    <body>

        <header>
            <b>TESIS LAB</b>

            <div style="margin-top:12px">
                <a href="{{ url_for('panel') }}">Panel principal</a>
                <a href="{{ url_for('innovaciones_inicio') }}">Innovaciones</a>
                <a href="{{ url_for('biblioteca') }}">Biblioteca</a>
                <a href="{{ url_for('logout') }}">Salir</a>
            </div>
        </header>

        <main>

            <h1>{{ titulo }}</h1>

            <p class="muted">{{ subtitulo }}</p>

            {{ contenido|safe }}

        </main>

    </body>
    </html>
    ''',
    titulo=titulo,
    contenido=contenido,
    subtitulo=subtitulo)



def fmt_estado_semaforo(estado, fecha_limite=None):
    if estado == "Aprobado": return ("verde", "Aprobado")
    if estado in ("Necesita correcciones", "Correcciones pendientes"): return ("rojo", "Necesita correcciones")
    if fecha_limite:
        try:
            if date.fromisoformat(str(fecha_limite)[:10]) < date.today(): return ("rojo", "Fecha vencida")
        except ValueError:
            pass
    return ("amarillo", "Pendiente de revisión")



@app.route("/innovaciones")
@login_requerido
def innovaciones_inicio():
    u = usuario_actual()

    if u["rol"] == "estudiante":
        destino = url_for("innovaciones_estudiante")
    elif u["rol"] == "tutor":
        destino = url_for("innovaciones_tutor")
    else:
        destino = url_for("innovaciones_admin")

    return render_template(
        "innovaciones/inicio.html",
        titulo="Centro de innovaciones",
        subtitulo="TESIS LAB · Centro de innovación académica",
        destino=destino
    )





@app.route("/innovaciones/estudiante")
@roles_requeridos("estudiante")
def innovaciones_estudiante():

    u = usuario_actual()

    with conectar_db() as db:

        # ========================================================
        # INVESTIGACIONES DEL ESTUDIANTE
        # ========================================================

        proyectos = db.execute("""
            SELECT
                i.*,
                g.nombre AS grupo_nombre
            FROM investigaciones i
            JOIN grupos g ON g.id = i.grupo_id
            JOIN miembros_grupo mg ON mg.grupo_id = g.id
            WHERE mg.estudiante_id = ?
              AND mg.estado = 'activo'
            ORDER BY i.creado_en DESC
        """, (u["id"],)).fetchall()

        ids_investigaciones = [p["id"] for p in proyectos]

        # ========================================================
        # VARIABLES DE LOS NUEVE LOGROS
        # ========================================================

        total_entregas = 0
        entregas_a_tiempo = 0
        reenvios_corregidos = 0
        tareas_terminadas = 0
        capitulos_aprobados = {}

        # ========================================================
        # CALCULAR LOGROS
        # ========================================================

        if ids_investigaciones:

            placeholders = ",".join(
                "?" for _ in ids_investigaciones
            )

            total_entregas = db.execute(f"""
                SELECT COUNT(*)
                FROM historial_entregas
                WHERE investigacion_id IN ({placeholders})
                  AND enviado_por = ?
            """, (*ids_investigaciones, u["id"])).fetchone()[0]

            entregas_a_tiempo = db.execute(f"""
                SELECT COUNT(*)
                FROM (
                    SELECT
                        investigacion_id,
                        nivel,
                        MIN(date(enviado_en)) AS primera_entrega
                    FROM historial_entregas
                    WHERE investigacion_id IN ({placeholders})
                      AND enviado_por = ?
                    GROUP BY investigacion_id, nivel
                )
                WHERE
                    (nivel = 1 AND primera_entrega <= '2026-08-18')
                    OR (nivel = 2 AND primera_entrega <= '2026-09-01')
                    OR (nivel = 3 AND primera_entrega <= '2026-09-22')
                    OR (nivel = 4 AND primera_entrega <= '2026-09-22')
                    OR (nivel = 5 AND primera_entrega <= '2026-10-27')
                    OR (nivel = 6 AND primera_entrega <= '2026-11-10')
            """, (*ids_investigaciones, u["id"])).fetchone()[0]

            reenvios_corregidos = db.execute(f"""
                SELECT COUNT(*)
                FROM historial_entregas h
                WHERE h.investigacion_id IN ({placeholders})
                  AND h.enviado_por = ?
                  AND h.version > 1
                  AND EXISTS (
                      SELECT 1
                      FROM historial_entregas anterior
                      JOIN observaciones_correccion oc
                        ON oc.historial_entrega_id = anterior.id
                      WHERE anterior.investigacion_id = h.investigacion_id
                        AND anterior.nivel = h.nivel
                        AND anterior.version = h.version - 1
                        AND oc.corregida = 1
                  )
            """, (*ids_investigaciones, u["id"])).fetchone()[0]

            tareas_terminadas = db.execute(f"""
                SELECT COUNT(*)
                FROM tareas_grupo
                WHERE investigacion_id IN ({placeholders})
                  AND responsable_id = ?
                  AND estado = 'Completada'
            """, (*ids_investigaciones, u["id"])).fetchone()[0]

            for numero in (1, 2, 3):

                capitulos_aprobados[numero] = db.execute(f"""
                    SELECT COUNT(*)
                    FROM niveles_investigacion
                    WHERE investigacion_id IN ({placeholders})
                      AND nivel = ?
                      AND estado = 'Aprobado'
                """, (*ids_investigaciones, numero)).fetchone()[0]

        # ========================================================
        # NUEVE LOGROS
        # ========================================================

        logros_panel = [

            {
                "codigo": "primera_entrega",
                "titulo": "Primera entrega",
                "descripcion": "Enviaste tu primer trabajo.",
                "actual": min(total_entregas, 1),
                "meta": 1
            },
            {
                "codigo": "siempre_a_tiempo",
                "titulo": "Siempre a tiempo",
                "descripcion": "3 entregas enviadas antes de la fecha límite.",
                "actual": min(entregas_a_tiempo, 3),
                "meta": 3
            },
            {
                "codigo": "constancia",
                "titulo": "Constancia",
                "descripcion": "5 entregas enviadas en total.",
                "actual": min(total_entregas, 5),
                "meta": 5
            },
            {
                "codigo": "capitulo_1",
                "titulo": "Capítulo 1 completado",
                "descripcion": "Perfil y tema aprobados.",
                "actual": min(capitulos_aprobados.get(1, 0), 1),
                "meta": 1
            },
            {
                "codigo": "capitulo_2",
                "titulo": "Capítulo 2 completado",
                "descripcion": "Marco teórico aprobado.",
                "actual": min(capitulos_aprobados.get(2, 0), 1),
                "meta": 1
            },
            {
                "codigo": "capitulo_3",
                "titulo": "Capítulo 3 completado",
                "descripcion": "Metodología y resultados aprobados.",
                "actual": min(capitulos_aprobados.get(3, 0), 1),
                "meta": 1
            },
            {
                "codigo": "aprendo_observaciones",
                "titulo": "Aprendo de las observaciones",
                "descripcion": "Reenviaste un trabajo corregido.",
                "actual": min(reenvios_corregidos, 1),
                "meta": 1
            },
            {
                "codigo": "mejora_continua",
                "titulo": "Mejora continua",
                "descripcion": "3 trabajos corregidos y reenviados.",
                "actual": min(reenvios_corregidos, 3),
                "meta": 3
            },
            {
                "codigo": "trabajo_equipo",
                "titulo": "Trabajo en equipo",
                "descripcion": "3 tareas del grupo terminadas.",
                "actual": min(tareas_terminadas, 3),
                "meta": 3
            }
        ]

        # ========================================================
        # GUARDAR LOGROS DESBLOQUEADOS
        # ========================================================

        for logro in logros_panel:

            if logro["actual"] >= logro["meta"]:

                existe = db.execute("""
                    SELECT id
                    FROM logros_academicos
                    WHERE usuario_id = ?
                      AND investigacion_id IS NULL
                      AND codigo = ?
                    LIMIT 1
                """, (u["id"], logro["codigo"])).fetchone()

                if not existe:
                    db.execute("""
                        INSERT INTO logros_academicos
                        (
                            usuario_id,
                            investigacion_id,
                            codigo,
                            titulo,
                            descripcion
                        )
                        VALUES (?, NULL, ?, ?, ?)
                    """, (
                        u["id"],
                        logro["codigo"],
                        logro["titulo"],
                        logro["descripcion"]
                    ))

    # ============================================================
    # CONTENEDOR PRINCIPAL
    # ============================================================

    html = """
    <div style="
        display: flex;
        flex-direction: column;
        gap: 22px;
        width: 100%;
        max-width: 1100px;
        margin: 0 auto;
    ">
    """

    # ========================================================
    # TARJETAS DE INVESTIGACIONES
    # ========================================================

    for p in proyectos:

        with conectar_db() as db:

            niveles = db.execute("""
                SELECT nivel, estado, observaciones
                FROM niveles_investigacion
                WHERE investigacion_id = ?
                ORDER BY nivel
            """, (p["id"],)).fetchall()

            pendientes = db.execute("""
                SELECT COUNT(*)
                FROM niveles_investigacion
                WHERE investigacion_id = ?
                  AND estado IN (
                      'Pendiente',
                      'Pendiente de revisión',
                      'Necesita correcciones'
                  )
            """, (p["id"],)).fetchone()[0]

            completados = db.execute("""
                SELECT COUNT(*)
                FROM niveles_investigacion
                WHERE investigacion_id = ?
                  AND estado = 'Aprobado'
            """, (p["id"],)).fetchone()[0]

            siguiente = db.execute("""
                SELECT titulo, fecha_limite
                FROM tareas_grupo
                WHERE investigacion_id = ?
                  AND estado != 'Completada'
                  AND fecha_limite IS NOT NULL
                  AND (
                      responsable_id = ?
                      OR responsable_id IS NULL
                  )
                ORDER BY date(fecha_limite) ASC
                LIMIT 1
            """, (p["id"], u["id"])).fetchone()

            total = db.execute("""
                SELECT COUNT(*)
                FROM niveles_investigacion
                WHERE investigacion_id = ?
            """, (p["id"],)).fetchone()[0]

            observaciones = db.execute("""
                SELECT COUNT(*)
                FROM observaciones_puntos
                WHERE investigacion_id = ?
                  AND corregida = 0
            """, (p["id"],)).fetchone()[0]

        avance = round(completados * 100 / max(total, 1))

        if siguiente:
            proxima = (
                f"Próxima tarea: {siguiente['titulo']} · "
                f"Límite: {siguiente['fecha_limite']}"
            )
        else:
            proxima = "No tienes tareas próximas asignadas."

        html += f"""
        <div class="card" style="
            width: 100%;
            box-sizing: border-box;
            margin: 0;
        ">

            <h2>{p['titulo']}</h2>

            <p class="muted">{p['grupo_nombre']}</p>

            <b>{avance}% de avance</b>

            <div class="barra">
                <span style="width: {avance}%"></span>
            </div>

            <p>
                {completados}/{total} capítulos aprobados
                · {pendientes} pendientes
                · {observaciones} observaciones por corregir
            </p>

            <p>{proxima}</p>

            <div style="
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
                margin-top: 18px;
            ">

                <a class="btn"
                   href="{url_for('progreso_investigacion', investigacion_id=p['id'])}">
                    Ver progreso y semáforo
                </a>

                <a class="btn secondary"
                   href="{url_for('guia_investigacion', investigacion_id=p['id'])}">
                    Guía académica
                </a>

                <a class="btn secondary"
                   href="{url_for('tareas_grupo_innovacion', investigacion_id=p['id'])}">
                    Tareas del grupo
                </a>

                <a class="btn secondary"
                   href="{url_for('mapa_conocimientos', investigacion_id=p['id'])}">
                    Mapa de conocimientos
                </a>

            </div>

        </div>
        """

   
    # ========================================================
    # BIBLIOTECA VIRTUAL
    # ========================================================

    html += f"""
        <div class="card" style="
            width: 100%;
            box-sizing: border-box;
            margin: 0;
        ">

            <a class="btn secondary"
               href="{url_for('biblioteca')}">
                📚 Buscar fuentes académicas
            </a>

        </div>

    </div>
    """

    return html_innovacion("Mi espacio de investigación", html)




@app.route("/innovaciones/logros")
@roles_requeridos("estudiante")
def innovaciones_logros():

    u = usuario_actual()

    with conectar_db() as db:

        # ========================================================
        # INVESTIGACIONES DEL ESTUDIANTE
        # ========================================================

        proyectos = db.execute("""
            SELECT i.id
            FROM investigaciones i
            JOIN grupos g ON g.id = i.grupo_id
            JOIN miembros_grupo mg ON mg.grupo_id = g.id
            WHERE mg.estudiante_id = ?
              AND mg.estado = 'activo'
        """, (u["id"],)).fetchall()

        ids = [p["id"] for p in proyectos]

        total_entregas = 0
        entregas_a_tiempo = 0
        reenvios_corregidos = 0
        tareas_terminadas = 0
        capitulos_aprobados = {}

        # ========================================================
        # CALCULAR ESTADÍSTICAS
        # ========================================================

        if ids:

            placeholders = ",".join("?" for _ in ids)

            total_entregas = db.execute(f"""
                SELECT COUNT(*)
                FROM historial_entregas
                WHERE investigacion_id IN ({placeholders})
                  AND enviado_por = ?
            """, (*ids, u["id"])).fetchone()[0]

            entregas_a_tiempo = db.execute(f"""
                SELECT COUNT(*)
                FROM (
                    SELECT investigacion_id, nivel,
                           MIN(date(enviado_en)) AS primera_entrega
                    FROM historial_entregas
                    WHERE investigacion_id IN ({placeholders})
                      AND enviado_por = ?
                    GROUP BY investigacion_id, nivel
                )
                WHERE
                    (nivel = 1 AND primera_entrega <= '2026-08-18')
                    OR (nivel = 2 AND primera_entrega <= '2026-09-01')
                    OR (nivel = 3 AND primera_entrega <= '2026-09-22')
                    OR (nivel = 4 AND primera_entrega <= '2026-10-13')
                    OR (nivel = 5 AND primera_entrega <= '2026-10-27')
                    OR (nivel = 6 AND primera_entrega <= '2026-11-10')
            """, (*ids, u["id"])).fetchone()[0]

            reenvios_corregidos = db.execute(f"""
                SELECT COUNT(*)
                FROM historial_entregas h
                WHERE h.investigacion_id IN ({placeholders})
                  AND h.enviado_por = ?
                  AND h.version > 1
                  AND EXISTS (
                      SELECT 1
                      FROM historial_entregas anterior
                      JOIN observaciones_correccion oc
                        ON oc.historial_entrega_id = anterior.id
                      WHERE anterior.investigacion_id = h.investigacion_id
                        AND anterior.nivel = h.nivel
                        AND anterior.version = h.version - 1
                        AND oc.corregida = 1
                  )
            """, (*ids, u["id"])).fetchone()[0]

            tareas_terminadas = db.execute(f"""
                SELECT COUNT(*)
                FROM tareas_grupo
                WHERE investigacion_id IN ({placeholders})
                  AND responsable_id = ?
                  AND estado = 'Completada'
            """, (*ids, u["id"])).fetchone()[0]

            for numero in (1, 2, 3):

                capitulos_aprobados[numero] = db.execute(f"""
                    SELECT COUNT(*)
                    FROM niveles_investigacion
                    WHERE investigacion_id IN ({placeholders})
                      AND nivel = ?
                      AND estado = 'Aprobado'
                """, (*ids, numero)).fetchone()[0]

    # ============================================================
    # DEFINICIÓN DE LOS NUEVE LOGROS
    # ============================================================

    logros = [

        {
            "codigo": "primera_entrega",
            "titulo": "Primera entrega",
            "descripcion": "Enviaste tu primer trabajo.",
            "actual": min(total_entregas, 1),
            "meta": 1,
            "icono": "🥇"
        },

        {
            "codigo": "siempre_a_tiempo",
            "titulo": "Siempre a tiempo",
            "descripcion": "3 entregas enviadas antes de la fecha límite.",
            "actual": min(entregas_a_tiempo, 3),
            "meta": 3,
            "icono": "⏱️"
        },

        {
            "codigo": "constancia",
            "titulo": "Constancia",
            "descripcion": "5 entregas enviadas en total.",
            "actual": min(total_entregas, 5),
            "meta": 5,
            "icono": "📚"
        },

        {
            "codigo": "capitulo_1",
            "titulo": "Capítulo 1 completado",
            "descripcion": "Perfil y tema aprobados.",
            "actual": min(capitulos_aprobados.get(1, 0), 1),
            "meta": 1,
            "icono": "🎓"
        },

        {
            "codigo": "capitulo_2",
            "titulo": "Capítulo 2 completado",
            "descripcion": "Marco teórico aprobado.",
            "actual": min(capitulos_aprobados.get(2, 0), 1),
            "meta": 1,
            "icono": "📖"
        },

        {
            "codigo": "capitulo_3",
            "titulo": "Capítulo 3 completado",
            "descripcion": "Metodología y resultados aprobados.",
            "actual": min(capitulos_aprobados.get(3, 0), 1),
            "meta": 1,
            "icono": "🔬"
        },

        {
            "codigo": "aprendo_observaciones",
            "titulo": "Aprendo de las observaciones",
            "descripcion": "Reenviaste un trabajo corregido.",
            "actual": min(reenvios_corregidos, 1),
            "meta": 1,
            "icono": "💡"
        },

        {
            "codigo": "mejora_continua",
            "titulo": "Mejora continua",
            "descripcion": "3 trabajos corregidos y reenviados.",
            "actual": min(reenvios_corregidos, 3),
            "meta": 3,
            "icono": "📈"
        },

        {
            "codigo": "trabajo_equipo",
            "titulo": "Trabajo en equipo",
            "descripcion": "3 tareas del grupo terminadas.",
            "actual": min(tareas_terminadas, 3),
            "meta": 3,
            "icono": "🤝"
        }
    ]

    # ============================================================
    # GUARDAR LOGROS DESBLOQUEADOS
    # ============================================================

    with conectar_db() as db:

        for logro in logros:

            if logro["actual"] >= logro["meta"]:

                existe = db.execute("""
                    SELECT id
                    FROM logros_academicos
                    WHERE usuario_id = ?
                      AND investigacion_id IS NULL
                      AND codigo = ?
                    LIMIT 1
                """, (u["id"], logro["codigo"])).fetchone()

                if not existe:

                    db.execute("""
                        INSERT INTO logros_academicos
                        (
                            usuario_id,
                            investigacion_id,
                            codigo,
                            titulo,
                            descripcion
                        )
                        VALUES (?, NULL, ?, ?, ?)
                    """, (
                        u["id"],
                        logro["codigo"],
                        logro["titulo"],
                        logro["descripcion"]
                    ))

    # ============================================================
    # RESUMEN GENERAL
    # ============================================================

    conseguidos = sum(
        1 for logro in logros
        if logro["actual"] >= logro["meta"]
    )

    porcentaje_general = round(conseguidos / 9 * 100)

    # ============================================================
    # ENCABEZADO
    # ============================================================

    html = f"""
    <div style="
        width: 100%;
        max-width: 1200px;
        margin: 0 auto;
        display: flex;
        flex-direction: column;
        gap: 22px;
    ">

        <div class="card" style="
            width: 100%;
            box-sizing: border-box;
            margin: 0;
        ">

            <h1>🏆 Mis logros académicos</h1>

            <p class="muted">
                Reconocemos tu constancia y tu esfuerzo por mejorar,
                no solamente tus calificaciones.
            </p>

            <h2>{conseguidos} de 9 logros conseguidos</h2>

            <div class="barra">
                <span style="width: {porcentaje_general}%"></span>
            </div>

            <p class="muted">
                {porcentaje_general}% de progreso general
            </p>

        </div>
    """

    # ============================================================
    # CUADRÍCULA DE CUATRO TARJETAS HORIZONTALES
    # ============================================================

    html += """
        <div id="cuadricula-logros" style="
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 18px;
            width: 100%;
            align-items: stretch;
        ">
    """

    for logro in logros:

        desbloqueado = logro["actual"] >= logro["meta"]

        porcentaje = logro["actual"] / logro["meta"] * 100

        estado = (
            "🏆 Conseguido"
            if desbloqueado
            else "🔒 En progreso"
        )

        color_borde = (
            "#D6AD48"
            if desbloqueado
            else "var(--borde, #ddd)"
        )

        html += f"""
        <div class="card" style="
            width: 100%;
            min-width: 0;
            min-height: 245px;
            box-sizing: border-box;
            margin: 0;
            padding: 18px;
            border: 1px solid {color_borde};
            border-radius: 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 16px;
        ">

            <div>

                <div style="
                    font-size: 38px;
                    margin-bottom: 14px;
                ">
                    {logro['icono']}
                </div>

                <h3 style="
                    margin: 0 0 9px 0;
                    font-size: 16px;
                    line-height: 1.4;
                ">
                    {logro['titulo']}
                </h3>

                <p class="muted" style="
                    font-size: 13px;
                    line-height: 1.5;
                    margin: 0;
                ">
                    {logro['descripcion']}
                </p>

            </div>

            <div>

                <b style="font-size: 13px;">
                    {estado}
                </b>

                <p style="
                    margin: 9px 0;
                    font-size: 13px;
                ">
                    {logro['actual']} de {logro['meta']}
                </p>

                <div class="barra">
                    <span style="width: {porcentaje}%"></span>
                </div>

            </div>

        </div>
        """

    html += """
        </div>

        <style>
            @media (max-width: 1000px) {
                #cuadricula-logros {
                    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
                }
            }

            @media (max-width: 550px) {
                #cuadricula-logros {
                    grid-template-columns: 1fr !important;
                }
            }
        </style>
    """

    # ============================================================
    # PIE DE PÁGINA
    # ============================================================

    html += """
        <div class="card" style="
            width: 100%;
            box-sizing: border-box;
            margin: 0;
        ">

            <p class="muted">
                Los logros se calculan automáticamente con tus entregas,
                reenvíos corregidos y tareas del grupo terminadas.
            </p>

            <a class="btn secondary"
               href="/innovaciones/estudiante">
                ← Volver a mi panel
            </a>

        </div>

    </div>
    """

    return html_innovacion("Mis logros académicos", html)



@app.route("/innovaciones/investigacion/<int:investigacion_id>/progreso")
@login_requerido
def progreso_investigacion(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u, investigacion_id): return "Sin permiso",403
    with conectar_db() as db:
        inv=db.execute("SELECT titulo FROM investigaciones WHERE id=?",(investigacion_id,)).fetchone()
        niveles=db.execute("SELECT n.*, (SELECT COUNT(*) FROM observaciones_puntos o WHERE o.investigacion_id=n.investigacion_id AND o.nivel=n.nivel AND o.corregida=0) obs FROM niveles_investigacion n WHERE investigacion_id=? ORDER BY nivel",(investigacion_id,)).fetchall()
        historial=db.execute("SELECT evento,fecha,nivel FROM historial_progreso WHERE investigacion_id=? ORDER BY fecha DESC LIMIT 20",(investigacion_id,)).fetchall()
    total=len(niveles); aprobados=sum(1 for n in niveles if n['estado']=='Aprobado'); avance=round(aprobados*100/max(total,1))
    html=f'<div class="card"><h2>{inv["titulo"]}</h2><h2>{avance}% completado</h2><div class="barra"><span style="width:{avance}%"></span></div><p>{aprobados} capítulos aprobados de {total}</p></div><div class="card"><h2>Semáforo de entregas</h2><table><tr><th>Nivel</th><th>Estado</th><th>Observaciones abiertas</th></tr>'
    for n in niveles:
        color,etiqueta=fmt_estado_semaforo(n['estado'])
        html+=f"<tr><td>Nivel {n['nivel']}</td><td><span class='pill {color}'>{etiqueta}</span></td><td>{n['obs']}</td></tr>"
    html+='</table></div><div class="card"><h2>Historial de progreso</h2>'
    html+=''.join(f"<p><b>{h['evento']}</b> · Nivel {h['nivel']} · {h['fecha']}</p>" for h in historial) or '<p>Sin movimientos registrados.</p>'
    html+='</div><div class="card"><a class="btn" href="'+url_for('guia_investigacion',investigacion_id=investigacion_id)+'">Abrir guía y correcciones</a> <a class="btn secondary" href="'+url_for('comparar_entregas',investigacion_id=investigacion_id)+'">Historial y comparar versiones</a></div>'
    return html_innovacion("Progreso de investigación",html)


@app.route("/innovaciones/investigacion/<int:investigacion_id>/guia", methods=["GET","POST"])
@login_requerido
def guia_investigacion(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id): return "Sin permiso",403
    if request.method=="POST":
        with conectar_db() as db:
            for apartado in ["Problema","Objetivo general","Objetivos específicos","Justificación","Metodología","Conclusiones","Bibliografía","Citas y referencias","Formato"]:
                valor=1 if request.form.get(_clave_checklist(apartado))=="1" else 0
                db.execute("UPDATE checklist_academico SET cumplido=?,actualizado_por=?,actualizado_en=CURRENT_TIMESTAMP WHERE investigacion_id=? AND apartado=?",(valor,u['id'],investigacion_id,apartado))
            auditar(db,"Actualizó guía académica","investigacion",investigacion_id)
        flash("Lista de verificación actualizada.","exito")
        return redirect(url_for("guia_investigacion",investigacion_id=investigacion_id))
    with conectar_db() as db:
        items=db.execute("SELECT * FROM checklist_academico WHERE investigacion_id=? ORDER BY id",(investigacion_id,)).fetchall()
        obs=db.execute("SELECT * FROM observaciones_puntos WHERE investigacion_id=? ORDER BY nivel,creada_en DESC",(investigacion_id,)).fetchall()
    html='<div class="card"><h2>Revisión de estructura académica</h2><p>Esta lista orienta la revisión; no garantiza calidad ni detecta plagio de forma infalible.</p><form method="post">'
    for it in items:
        key=_clave_checklist(it['apartado'])
        checked='checked' if it['cumplido'] else ''
        html+=f'<label><input style="width:auto" type="checkbox" name="{key}" value="1" {checked}> {it["apartado"]}</label><br>'
    html+='<button>Guardar checklist</button></form></div><div class="card"><h2>Observaciones del tutor</h2>'
    for o in obs:
        color='verde' if o['corregida'] else 'amarillo'
        html+=f'<p><span class="pill {color}">{"Corregida" if o["corregida"] else "Pendiente"}</span> Nivel {o["nivel"]}: {o["texto"]}</p>'
        if u['rol']=='estudiante' and not o['corregida']:
            html+=f'<form method="post" action="{url_for("marcar_observacion_corregida",observacion_id=o["id"])}"><button class="secondary">Marcar como corregida</button></form>'
    html+='</div>'
    if u['rol'] in ('admin','tutor'):
        html+=f'''<div class="card"><h2>Agregar observaciones separadas</h2><p>Escribe una observación por línea.</p><form method="post" action="{url_for('crear_observaciones',investigacion_id=investigacion_id)}"><label>Nivel</label><select name="nivel">'''+''.join(f'<option value="{n}">Nivel {n}</option>' for n in range(1,7))+'''</select><label>Observaciones</label><textarea name="observaciones" rows="5" required></textarea><button>Guardar observaciones</button></form></div>'''
    html+=f'<div class="card"><a class="btn" href="{url_for("asistente_investigacion",investigacion_id=investigacion_id)}">Abrir asistente de investigación</a></div>'
    return html_innovacion("Guía para mejorar el trabajo",html)


# ============================================================
# REGISTRAR OBSERVACIONES DE UNA INVESTIGACIÓN
# ============================================================

@app.route(
    "/innovaciones/investigacion/<int:investigacion_id>/observaciones",
    methods=["POST"]
)
@roles_requeridos("admin", "tutor")
def crear_observaciones(investigacion_id):

    usuario = usuario_actual()

    # ========================================================
    # VERIFICAR ACCESO A LA INVESTIGACIÓN
    # ========================================================

    if not exigir_acceso_investigacion(
        usuario,
        investigacion_id
    ):
        return "Sin permiso", 403

    # ========================================================
    # OBTENER DATOS DEL FORMULARIO
    # ========================================================

    nivel = request.form.get(
        "nivel",
        type=int
    )

    observaciones_texto = request.form.get(
        "observaciones",
        ""
    )

    # Separar las observaciones por líneas
    # y eliminar viñetas o caracteres innecesarios.

    textos = [
        texto.strip(" •-*\t")
        for texto in observaciones_texto.splitlines()
        if texto.strip(" •-*\t")
    ]

    # ========================================================
    # VALIDAR INFORMACIÓN
    # ========================================================

    if nivel not in range(1, 7) or not textos:

        flash(
            "Indica el nivel y al menos una observación.",
            "error"
        )

    else:

        with conectar_db() as db:

            # ====================================================
            # OBTENER LA ÚLTIMA ENTREGA DEL NIVEL
            # ====================================================

            historial = db.execute(
                """
                SELECT id
                FROM historial_entregas
                WHERE investigacion_id = ?
                  AND nivel = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (
                    investigacion_id,
                    nivel
                )
            ).fetchone()

            historial_id = (
                historial["id"]
                if historial
                else None
            )

            # ====================================================
            # GUARDAR OBSERVACIONES INDIVIDUALES
            # ====================================================

            for texto in textos[:30]:

                db.execute(
                    """
                    INSERT INTO observaciones_puntos (
                        investigacion_id,
                        nivel,
                        historial_id,
                        texto,
                        creada_por
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        investigacion_id,
                        nivel,
                        historial_id,
                        texto,
                        usuario["id"]
                    )
                )

            # ====================================================
            # REGISTRAR ACCIÓN EN AUDITORÍA
            # ====================================================

            auditar(
                db,
                "Registró observaciones",
                "investigacion",
                investigacion_id,
                f"Nivel {nivel}: {len(textos)} observaciones"
            )

            # ====================================================
            # OBTENER INTEGRANTES DEL GRUPO
            # ====================================================

            miembros = db.execute(
                """
                SELECT estudiante_id
                FROM miembros_grupo mg
                JOIN investigaciones i
                    ON i.grupo_id = mg.grupo_id
                WHERE i.id = ?
                  AND mg.estado = 'activo'
                """,
                (investigacion_id,)
            ).fetchall()

            # ====================================================
            # NOTIFICAR A LOS ESTUDIANTES
            # ====================================================

            for miembro in miembros:

                crear_notificacion(
                    db,
                    miembro["estudiante_id"],
                    "Nuevas observaciones",
                    (
                        f"El tutor agregó {len(textos)} "
                        f"observaciones al Nivel {nivel}."
                    ),
                    investigacion_id,
                    url_for(
                        "guia_investigacion",
                        investigacion_id=investigacion_id
                    )
                )

        # ====================================================
        # MENSAJE DE CONFIRMACIÓN
        # ====================================================

        flash(
            "Observaciones guardadas por separado.",
            "exito"
        )

    # ========================================================
    # REGRESAR A LA GUÍA DE INVESTIGACIÓN
    # ========================================================

    return redirect(
        url_for(
            "guia_investigacion",
            investigacion_id=investigacion_id
        )
    )


@app.route("/innovaciones/observaciones/<int:observacion_id>/corregir",methods=["POST"])
@roles_requeridos("estudiante")
def marcar_observacion_corregida(observacion_id):
    u=usuario_actual()
    with conectar_db() as db:
        o=db.execute("SELECT * FROM observaciones_puntos WHERE id=?",(observacion_id,)).fetchone()
        if not o or not es_miembro_investigacion(u['id'],o['investigacion_id']): return "Sin permiso",403
        db.execute("UPDATE observaciones_puntos SET corregida=1,corregida_por=?,corregida_en=CURRENT_TIMESTAMP WHERE id=?",(u['id'],observacion_id))
        auditar(db,"Marcó observación corregida","observacion",observacion_id)
    flash("Observación marcada. Recuerda volver a enviar el archivo corregido.","exito")
    return redirect(url_for("guia_investigacion",investigacion_id=o['investigacion_id']))


@app.route("/innovaciones/investigacion/<int:investigacion_id>/asistente",methods=["GET","POST"])
@login_requerido
def asistente_investigacion(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id): return "Sin permiso",403
    if request.method=="POST":
        with conectar_db() as db:
            for campo in ("Problema","Objetivo general","Objetivos específicos","Justificación","Metodología","Conclusiones","Bibliografía"):
                valor=request.form.get(campo.lower().replace(" ","_"),"").strip()
                db.execute("INSERT INTO mapa_conocimientos(investigacion_id,elemento,contenido,actualizado_por) VALUES(?,?,?,?) ON CONFLICT(investigacion_id,elemento) DO UPDATE SET contenido=excluded.contenido,actualizado_por=excluded.actualizado_por,actualizado_en=CURRENT_TIMESTAMP",(investigacion_id,campo,valor,u['id']))
            auditar(db,"Actualizó mapa de conocimientos","investigacion",investigacion_id)
        flash("Tus ideas quedaron organizadas en el mapa de conocimientos.","exito")
    with conectar_db() as db: datos={x['elemento']:x['contenido'] for x in db.execute("SELECT * FROM mapa_conocimientos WHERE investigacion_id=?",(investigacion_id,)).fetchall()}
    prompts={"Problema":"¿Qué situación concreta quieres estudiar, dónde ocurre y a quién afecta?","Objetivo general":"Comienza con un verbo en infinitivo y expresa qué resultado buscas.","Objetivos específicos":"Divide el objetivo general en pasos observables y ordenados.","Justificación":"Explica por qué importa el problema, a quién beneficia y qué aporta el estudio.","Metodología":"Indica enfoque, diseño, población/muestra, técnicas e instrumentos.","Conclusiones":"Responde a los objetivos usando los resultados obtenidos; no agregues datos nuevos.","Bibliografía":"Registra autor, año, título, editorial o revista y DOI/URL verificable."}
    html='<div class="card"><p>Asistente orientativo: organiza tus ideas y revisa la coherencia. No sustituye al tutor ni inventa fuentes.</p><form method="post">'
    for campo,prompt in prompts.items(): html+=f'<label>{campo}</label><p class="muted">{prompt}</p><textarea name="{campo.lower().replace(" ","_")}" rows="3">{datos.get(campo,"")}</textarea>'
    html+='<button>Guardar y organizar ideas</button></form></div><div class="card"><h2>Pasos sugeridos</h2><ol><li>Delimita el problema y formula una pregunta investigable.</li><li>Asegura que los objetivos respondan a esa pregunta.</li><li>Justifica la relevancia y define una metodología viable.</li><li>Comprueba que las conclusiones se apoyen en resultados.</li><li>Verifica cada referencia en su fuente original.</li></ol></div>'
    return html_innovacion("Asistente de investigación",html)




@app.route(
    "/innovaciones/investigacion/<int:investigacion_id>/tareas-grupo",
    methods=["GET", "POST"]
)
@login_requerido
def tareas_grupo_innovacion(investigacion_id):

    usuario = usuario_actual()

    if not exigir_acceso_investigacion(usuario, investigacion_id):
        return "Sin permiso", 403

    with conectar_db() as db:

        # ====================================================
        # DATOS DE LA INVESTIGACIÓN Y DEL GRUPO
        # ====================================================

        investigacion = db.execute(
            """
            SELECT
                i.id,
                i.titulo,
                i.grupo_id,
                g.nombre AS grupo_nombre,
                g.lider_id
            FROM investigaciones i
            LEFT JOIN grupos g
                ON g.id = i.grupo_id
            WHERE i.id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        if not investigacion:
            return "Investigación no encontrada", 404

        if not investigacion["grupo_id"]:
            return "Esta investigación todavía no tiene un grupo asignado.", 400

        # ====================================================
        # VERIFICAR SI PUEDE ASIGNAR TAREAS
        # ====================================================

        miembro_actual = db.execute(
            """
            SELECT es_lider
            FROM miembros_grupo
            WHERE grupo_id = ?
              AND estudiante_id = ?
              AND estado = 'activo'
            """,
            (investigacion["grupo_id"], usuario["id"])
        ).fetchone()

        es_lider = (
            investigacion["lider_id"] == usuario["id"]
            or (
                miembro_actual
                and miembro_actual["es_lider"] == 1
            )
        )

        puede_asignar = (
            usuario["rol"] in ("admin", "tutor")
            or es_lider
        )

        # ====================================================
        # CREAR TAREA
        # ====================================================

        if request.method == "POST":

            if not puede_asignar:
                return "No tienes permiso para asignar tareas.", 403

            titulo = request.form.get(
                "titulo",
                ""
            ).strip()

            descripcion = request.form.get(
                "descripcion",
                ""
            ).strip()

            responsable_id = request.form.get(
                "responsable_id",
                type=int
            )

            fecha_limite = request.form.get(
                "fecha_limite"
            ) or None

            if not titulo:

                flash(
                    "El título de la tarea es obligatorio.",
                    "error"
                )

            elif responsable_id and not db.execute(
                """
                SELECT 1
                FROM miembros_grupo
                WHERE grupo_id = ?
                  AND estudiante_id = ?
                  AND estado = 'activo'
                """,
                (
                    investigacion["grupo_id"],
                    responsable_id
                )
            ).fetchone():

                return "El responsable no pertenece a este grupo.", 400

            else:

                db.execute(
                    """
                    INSERT INTO tareas_grupo (
                        investigacion_id,
                        titulo,
                        descripcion,
                        responsable_id,
                        fecha_limite,
                        estado,
                        creada_por
                    )
                    VALUES (?, ?, ?, ?, ?, 'Pendiente', ?)
                    """,
                    (
                        investigacion_id,
                        titulo,
                        descripcion,
                        responsable_id,
                        fecha_limite,
                        usuario["id"]
                    )
                )

                auditar(
                    db,
                    "Creó tarea grupal",
                    "investigacion",
                    investigacion_id,
                    titulo
                )

                flash(
                    "Tarea asignada correctamente.",
                    "exito"
                )

            return redirect(
                url_for(
                    "tareas_grupo_innovacion",
                    investigacion_id=investigacion_id
                )
            )

        # ====================================================
        # INTEGRANTES Y RENDIMIENTO
        # ====================================================

        miembros = db.execute(
            """
            SELECT
                u.id,
                u.nombre,
                u.apellido,
                COUNT(tg.id) AS total,
                COALESCE(
                    SUM(
                        CASE
                            WHEN tg.estado = 'Completada' THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS terminadas
            FROM miembros_grupo mg
            JOIN usuarios u
                ON u.id = mg.estudiante_id
            LEFT JOIN tareas_grupo tg
                ON tg.responsable_id = u.id
               AND tg.investigacion_id = ?
            WHERE mg.grupo_id = ?
              AND mg.estado = 'activo'
            GROUP BY u.id, u.nombre, u.apellido
            ORDER BY u.apellido, u.nombre
            """,
            (
                investigacion_id,
                investigacion["grupo_id"]
            )
        ).fetchall()

        # ====================================================
        # CONTADORES GENERALES
        # ====================================================

        resumen = db.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(
                    SUM(
                        CASE
                            WHEN estado = 'Completada' THEN 1
                            ELSE 0
                        END
                    ),
                    0
                ) AS terminadas
            FROM tareas_grupo
            WHERE investigacion_id = ?
            """,
            (investigacion_id,)
        ).fetchone()

        total_tareas = resumen["total"]
        total_terminadas = resumen["terminadas"]

        # ====================================================
        # FILTRO DE TAREAS
        # ====================================================

        filtro = request.args.get(
            "filtro",
            "Todas"
        )

        if filtro not in ("Todas", "Pendientes", "Terminadas"):
            filtro = "Todas"

        consulta = """
            SELECT
                tg.*,
                u.nombre,
                u.apellido,
                CASE
                    WHEN tg.estado != 'Completada'
                     AND tg.fecha_limite IS NOT NULL
                     AND date(tg.fecha_limite) < date('now', 'localtime')
                    THEN 1
                    ELSE 0
                END AS atrasada
            FROM tareas_grupo tg
            LEFT JOIN usuarios u
                ON u.id = tg.responsable_id
            WHERE tg.investigacion_id = ?
        """

        parametros = [investigacion_id]

        if filtro == "Pendientes":

            consulta += """
                AND tg.estado != 'Completada'
            """

        elif filtro == "Terminadas":

            consulta += """
                AND tg.estado = 'Completada'
            """

        consulta += """
            ORDER BY
                CASE
                    WHEN tg.estado = 'Completada' THEN 1
                    ELSE 0
                END,
                date(tg.fecha_limite) ASC,
                tg.id DESC
        """

        tareas = db.execute(
            consulta,
            parametros
        ).fetchall()

    # ========================================================
    # MOSTRAR PLANTILLA
    # ========================================================

    return render_template(
        "tareas_grupo.html",
        investigacion=investigacion,
        usuario=usuario,
        miembros=miembros,
        tareas=tareas,
        filtro=filtro,
        total_tareas=total_tareas,
        total_terminadas=total_terminadas,
        puede_asignar=puede_asignar
    )





# ============================================================
# COMPLETAR TAREA GRUPAL
# ============================================================

@app.route(
    "/innovaciones/tareas-grupo/<int:tarea_id>/completar",
    methods=["POST"]
)
@login_requerido
def completar_tarea_grupal(tarea_id):

    u = usuario_actual()

    with conectar_db() as db:

        # BUSCAR TAREA

        tarea = db.execute(
            """
            SELECT *
            FROM tareas_grupo
            WHERE id = ?
            """,
            (tarea_id,)
        ).fetchone()

        # VERIFICAR PERMISOS

        if not tarea:

            return "Tarea no encontrada", 404

        if not exigir_acceso_investigacion(
            u,
            tarea["investigacion_id"]
        ):

            return "Sin permiso", 403

        # VERIFICAR RESPONSABLE

        if (
            u["rol"] == "estudiante"
            and tarea["responsable_id"] != u["id"]
        ):
            return (
            "Solo el responsable asignado puede completar esta tarea.",
            403
        )

        # MARCAR COMO COMPLETADA

        db.execute(
            """
            UPDATE tareas_grupo
            SET
                estado = 'Completada',
                completada_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (tarea_id,)
        )

        # REGISTRAR ACTIVIDAD

        auditar(
            db,
            "Completó tarea grupal",
            "tarea_grupal",
            tarea_id
        )

    # VOLVER AL TABLERO DE TAREAS

    return redirect(
        url_for(
            "tareas_grupo_innovacion",
            investigacion_id=tarea["investigacion_id"]
        )
    )



# 6 Buscador de biblioteca virtual
@app.route("/innovaciones/biblioteca")
@login_requerido
def buscar_biblioteca():
    q=request.args.get('q','').strip(); tipo=request.args.get('tipo','').strip(); area=request.args.get('area','').strip()
    sql="SELECT * FROM recursos_biblioteca WHERE 1=1"; args=[]
    if q: sql+=" AND (titulo LIKE ? OR descripcion LIKE ?)"; args += [f'%{q}%',f'%{q}%']
    if tipo: sql+=" AND tipo=?"; args.append(tipo)
    if area: sql+=" AND area_principal=?"; args.append(area)
    sql+=" ORDER BY creado_en DESC LIMIT 100"
    with conectar_db() as db: recursos=db.execute(sql,args).fetchall()
    html=f'''<div class="card"><form><label>Tema</label><input name="q" value="{q}" placeholder="Ej. contaminación, nutrición..."><label>Tipo</label><select name="tipo"><option value="">Todos</option><option>Libro</option><option>Artículo</option><option>Guía</option><option>Monografía</option><option>Video</option></select><label>Área</label><input name="area" value="{area}" placeholder="Área de investigación"><button>Buscar</button></form></div><div class="card"><h2>Resultados ({len(recursos)})</h2>'''
    for r in recursos: html+=f'<p><b>{r["titulo"]}</b> · {r["tipo"] or "Recurso"} · {r["area_principal"] or "Sin área"}<br>{r["descripcion"] or ""}<br>{("<a target=_blank rel=noopener href="+r["url"]+">Abrir recurso</a>") if r["url"] else "Archivo disponible en Biblioteca Virtual"}</p>'
    html+='</div>'
    return html_innovacion("Buscador de fuentes académicas",html)


# 9-16 Módulo tutor
@app.route("/innovaciones/tutor")
@roles_requeridos("admin","tutor")
def innovaciones_tutor():
    u=usuario_actual()
    with conectar_db() as db:
        where="" if u['rol']=='admin' else "WHERE i.profesor_id=?"
        args=() if u['rol']=='admin' else (u['id'],)
        resumen=db.execute(f"""SELECT COUNT(*) proyectos, SUM(CASE WHEN i.estado='En revisión' THEN 1 ELSE 0 END) revisiones, SUM(CASE WHEN i.estado='Correcciones pendientes' THEN 1 ELSE 0 END) correcciones FROM investigaciones i {where}""",args).fetchone()
        reuniones=db.execute("SELECT COUNT(*) FROM solicitudes_reunion sr JOIN investigaciones i ON i.id=sr.investigacion_id WHERE sr.estado='Pendiente'"+("" if u['rol']=='admin' else " AND i.profesor_id=?"),args).fetchone()[0]
    html=f'''<div class="grid"><div class="card"><h2>{resumen['proyectos'] or 0}</h2><p>Investigaciones dirigidas</p></div><div class="card"><h2>{resumen['revisiones'] or 0}</h2><p>Entregas en revisión</p></div><div class="card"><h2>{resumen['correcciones'] or 0}</h2><p>Grupos con correcciones</p></div><div class="card"><h2>{reuniones}</h2><p>Solicitudes de reunión pendientes</p></div></div><div class="grid">'''
    for label,endpoint in [("Centro de tareas pendientes","centro_tareas_tutor"),("Seguimiento de grupos","seguimiento_grupos_tutor"),("Agenda y compromisos","agenda_tutor"),("Estadísticas del tutor","estadisticas_tutor")]: html+=f'<div class="card"><h2>{label}</h2><a class="btn" href="{url_for(endpoint)}">Abrir</a></div>'
    html+='</div>'
    return html_innovacion("Centro de trabajo del tutor",html)


# ============================================================
# CENTRO DE TAREAS PENDIENTES DEL TUTOR
# ============================================================

@app.route("/innovaciones/tutor/tareas-pendientes")
@roles_requeridos("admin", "tutor")
def centro_tareas_tutor():

    usuario = usuario_actual()

    with conectar_db() as db:

        # ====================================================
        # ENTREGAS PENDIENTES
        # ====================================================

        if usuario["rol"] == "admin":

            entregas = db.execute("""
                SELECT
                    e.id AS entrega_id,
                    e.nivel,
                    e.estado,
                    e.enviado_en,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo
                FROM entregas e
                JOIN investigaciones i
                    ON i.id = e.investigacion_id
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE e.estado IN (
                    'Pendiente',
                    'Pendiente de revisión',
                    'En revisión'
                )
                AND i.finalizada = 0
                ORDER BY e.enviado_en ASC
            """).fetchall()

            reuniones = db.execute("""
                SELECT
                    sr.*,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo
                FROM solicitudes_reunion sr
                JOIN investigaciones i
                    ON i.id = sr.investigacion_id
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE sr.estado = 'Pendiente'
                ORDER BY
                    sr.fecha_solicitada,
                    sr.hora_solicitada
            """).fetchall()

        else:

            entregas = db.execute("""
                SELECT
                    e.id AS entrega_id,
                    e.nivel,
                    e.estado,
                    e.enviado_en,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo
                FROM entregas e
                JOIN investigaciones i
                    ON i.id = e.investigacion_id
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                  AND i.finalizada = 0
                  AND e.estado IN (
                      'Pendiente',
                      'Pendiente de revisión',
                      'En revisión'
                  )
                ORDER BY e.enviado_en ASC
            """, (usuario["id"],)).fetchall()

            reuniones = db.execute("""
                SELECT
                    sr.*,
                    i.id AS investigacion_id,
                    i.titulo,
                    g.nombre AS grupo
                FROM solicitudes_reunion sr
                JOIN investigaciones i
                    ON i.id = sr.investigacion_id
                JOIN grupos g
                    ON g.id = i.grupo_id
                WHERE i.profesor_id = ?
                  AND sr.estado = 'Pendiente'
                ORDER BY
                    sr.fecha_solicitada,
                    sr.hora_solicitada
            """, (usuario["id"],)).fetchall()

    return render_template(
        "centro_tareas_tutor.html",
        usuario=usuario,
        entregas=entregas,
        reuniones=reuniones
    )


@app.route("/innovaciones/tutor/grupos")
@roles_requeridos("admin","tutor")
def seguimiento_grupos_tutor():
    u=usuario_actual()
    with conectar_db() as db:
        filtro="" if u['rol']=='admin' else "WHERE i.profesor_id=?"; args=() if u['rol']=='admin' else (u['id'],)
        rows=db.execute(f"""SELECT i.id,i.titulo,i.estado,g.nombre grupo,COUNT(DISTINCT mg.estudiante_id) integrantes,(SELECT COUNT(*) FROM niveles_investigacion n WHERE n.investigacion_id=i.id AND n.estado='Aprobado') aprobados,(SELECT COUNT(*) FROM observaciones_puntos o WHERE o.investigacion_id=i.id AND o.corregida=0) obs,(SELECT MAX(h.enviado_en) FROM historial_entregas h WHERE h.investigacion_id=i.id) ultima FROM investigaciones i JOIN grupos g ON g.id=i.grupo_id LEFT JOIN miembros_grupo mg ON mg.grupo_id=g.id AND mg.estado='activo' {filtro} GROUP BY i.id ORDER BY aprobados ASC""",args).fetchall()
    html='<div class="card"><table><tr><th>Grupo / investigación</th><th>Integrantes</th><th>Aprobados</th><th>Observaciones abiertas</th><th>Última entrega</th><th></th></tr>'
    for r in rows: html+=f'<tr><td>{r["grupo"]}<br>{r["titulo"]}</td><td>{r["integrantes"]}</td><td>{r["aprobados"]}/6</td><td>{r["obs"]}</td><td>{r["ultima"] or "Sin entregas"}</td><td><a href="{url_for("ficha_grupo",investigacion_id=r["id"])}">Ficha</a></td></tr>'
    html+='</table></div>'
    return html_innovacion("Seguimiento de todos los grupos",html)



@app.route("/innovaciones/investigacion/<int:investigacion_id>/ficha")
@login_requerido
def ficha_grupo(investigacion_id):

    u = usuario_actual()

    if not exigir_acceso_investigacion(u, investigacion_id):
        return "Sin permiso", 403

    with conectar_db() as db:

        inv = db.execute("""
            SELECT
                i.*,
                g.nombre AS grupo
            FROM investigaciones i
            JOIN grupos g ON g.id = i.grupo_id
            WHERE i.id = ?
        """, (investigacion_id,)).fetchone()

        miembros = db.execute("""
            SELECT
                u.nombre,
                u.apellido,
                u.usuario
            FROM miembros_grupo mg
            JOIN usuarios u ON u.id = mg.estudiante_id
            JOIN investigaciones i ON i.grupo_id = mg.grupo_id
            WHERE i.id = ?
              AND mg.estado = 'activo'
        """, (investigacion_id,)).fetchall()

        obs = db.execute("""
            SELECT
                nivel,
                texto,
                corregida,
                creada_en
            FROM observaciones_puntos
            WHERE investigacion_id = ?
            ORDER BY creada_en DESC
            LIMIT 10
        """, (investigacion_id,)).fetchall()

        tareas = db.execute("""
            SELECT
                titulo,
                estado,
                fecha_limite
            FROM tareas_grupo
            WHERE investigacion_id = ?
            ORDER BY fecha_limite
        """, (investigacion_id,)).fetchall()

    html = f"""
    <div style="
        display: flex;
        flex-direction: column;
        gap: 20px;
        width: 100%;
        max-width: 1100px;
        margin: 0 auto;
    ">

        <!-- INFORMACIÓN DEL GRUPO -->

        <div class="card" style="width: 100%; box-sizing: border-box;">

            <h2>{inv['grupo']} · {inv['titulo']}</h2>

            <p>
                <b>Área:</b>
                {inv['area_principal']} / {inv['subarea']}
            </p>

            <p>
                <b>Estado:</b>
                {inv['estado']}
            </p>

        </div>

        <!-- INTEGRANTES -->

        <div class="card" style="width: 100%; box-sizing: border-box;">

            <h2>👥 Integrantes del grupo</h2>

            {"".join(
                f"<p>👤 {m['nombre']} {m['apellido']} · {m['usuario']}</p>"
                for m in miembros
            ) or '<p class="muted">No hay integrantes registrados.</p>'}

        </div>

        <!-- PRÓXIMOS COMPROMISOS -->

        <div class="card" style="width: 100%; box-sizing: border-box;">

            <h2>📅 Próximos compromisos</h2>

            {"".join(
                f"<p><b>{t['titulo']}</b><br>"
                f"Estado: {t['estado']}<br>"
                f"Fecha límite: {t['fecha_limite'] or 'Sin fecha'}</p>"
                for t in tareas
            ) or '<p class="muted">No hay compromisos registrados.</p>'}

        </div>

        <!-- OBSERVACIONES -->

        <div class="card" style="width: 100%; box-sizing: border-box;">

            <h2>📝 Últimas observaciones</h2>

            {"".join(
                f"<p><b>Nivel {o['nivel']}</b><br>"
                f"{o['texto']}<br>"
                f"<span class='muted'>"
                f"{'✓ Corregida' if o['corregida'] else 'Pendiente'}"
                f" · {o['creada_en']}</span></p>"
                for o in obs
            ) or '<p class="muted">No hay observaciones registradas.</p>'}

        </div>

    </div>
    """

    return html_innovacion("Ficha de seguimiento del grupo", html)


@app.route("/innovaciones/tutor/estadisticas")
@roles_requeridos("admin","tutor")
def estadisticas_tutor():
    u=usuario_actual()
    with conectar_db() as db:
        filtro="" if u['rol']=='admin' else "AND i.profesor_id=?"; args=() if u['rol']=='admin' else (u['id'],)
        total=db.execute("SELECT COUNT(*) FROM investigaciones i WHERE 1=1 "+filtro,args).fetchone()[0]
        aprob=db.execute("SELECT COUNT(*) FROM niveles_investigacion n JOIN investigaciones i ON i.id=n.investigacion_id WHERE n.estado='Aprobado' "+filtro,args).fetchone()[0]
        revis=db.execute("SELECT COUNT(*) FROM entregas e JOIN investigaciones i ON i.id=e.investigacion_id WHERE e.estado IN ('Pendiente','Pendiente de revisión') "+filtro,args).fetchone()[0]
        revisadas=db.execute("SELECT COUNT(*) FROM historial_entregas h JOIN investigaciones i ON i.id=h.investigacion_id WHERE h.revisado_en IS NOT NULL "+filtro,args).fetchone()[0]
    html=f'<div class="grid">'+''.join(f'<div class="card"><h2>{v}</h2><p>{k}</p></div>' for k,v in [("Trabajos dirigidos",total),("Capítulos aprobados",aprob),("Entregas pendientes",revis),("Versiones revisadas",revisadas)])+'</div><div class="card"><p>Los indicadores se calculan con los registros guardados en TESIS LAB.</p></div>'
    return html_innovacion("Estadísticas de seguimiento",html)


# 10 Rúbrica configurable y puntuación detallada
@app.route("/innovaciones/investigacion/<int:investigacion_id>/rubrica",methods=["GET","POST"])
@roles_requeridos("admin","tutor")
def rubrica_avanzada(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id): return "Sin permiso",403
    nivel=request.values.get('nivel',1,type=int)
    if nivel not in range(1,7): nivel=1
    with conectar_db() as db:
        if request.method=='POST':
            criterios=[x.strip() for x in request.form.get('criterios','').splitlines() if x.strip()]
            if not criterios: flash("Agrega al menos un criterio.","error")
            else:
                for c in criterios[:20]: db.execute("INSERT OR IGNORE INTO criterios_rubrica(investigacion_id,nivel,criterio,puntaje_maximo) VALUES(?,?,?,?)",(investigacion_id,nivel,c,request.form.get('maximo',20,type=float)))
                auditar(db,"Configuró rúbrica","investigacion",investigacion_id,f"Nivel {nivel}")
                flash("Criterios guardados.","exito")
        criterios=db.execute("SELECT * FROM criterios_rubrica WHERE investigacion_id=? AND nivel=? ORDER BY id",(investigacion_id,nivel)).fetchall()
        notas=db.execute("SELECT nd.*,cr.criterio,cr.puntaje_maximo,u.nombre,u.apellido FROM notas_rubrica_detalle nd JOIN criterios_rubrica cr ON cr.id=nd.criterio_id JOIN usuarios u ON u.id=nd.evaluador_id WHERE cr.investigacion_id=? AND cr.nivel=? ORDER BY nd.evaluado_en DESC",(investigacion_id,nivel)).fetchall()
    html=f'<div class="card"><form method="get"><label>Nivel</label><select name="nivel">'+''.join(f'<option value="{n}" {"selected" if n==nivel else ""}>{n}</option>' for n in range(1,7))+'</select><button>Ver nivel</button></form></div>'
    html+=f'<div class="card"><h2>Configurar criterios · Nivel {nivel}</h2><form method="post"><input type="hidden" name="nivel" value="{nivel}"><label>Un criterio por línea</label><textarea name="criterios" required placeholder="Claridad del problema&#10;Coherencia metodológica&#10;Uso de fuentes"></textarea><label>Puntaje máximo por criterio</label><input name="maximo" type="number" min="1" max="100" value="20"><button>Guardar criterios</button></form></div>'
    for c in criterios:
        html+=f'<div class="card"><b>{c["criterio"]}</b> · Máximo {c["puntaje_maximo"]}<form method="post" action="{url_for("calificar_criterio",criterio_id=c["id"])}"><label>Puntaje</label><input type="number" step="0.1" min="0" max="{c["puntaje_maximo"]}" name="puntaje" required><label>Comentario</label><input name="comentario"><button>Guardar calificación</button></form></div>'
    return html_innovacion("Rúbricas configurables",html)


@app.route("/innovaciones/rubrica/criterio/<int:criterio_id>/calificar",methods=["POST"])
@roles_requeridos("admin","tutor")
def calificar_criterio(criterio_id):
    u=usuario_actual(); puntaje=request.form.get('puntaje',type=float); comentario=request.form.get('comentario','').strip()
    with conectar_db() as db:
        c=db.execute("SELECT cr.*,i.profesor_id FROM criterios_rubrica cr JOIN investigaciones i ON i.id=cr.investigacion_id WHERE cr.id=?",(criterio_id,)).fetchone()
        if not c or (u['rol']=='tutor' and c['profesor_id']!=u['id']): return "Sin permiso",403
        if puntaje is None or puntaje<0 or puntaje>c['puntaje_maximo']: return "Puntaje inválido",400
        db.execute("INSERT INTO notas_rubrica_detalle(criterio_id,evaluador_id,puntaje,comentario) VALUES(?,?,?,?)",(criterio_id,u['id'],puntaje,comentario)); auditar(db,"Calificó criterio","criterio_rubrica",criterio_id,str(puntaje))
    flash("Puntaje registrado.","exito")
    return redirect(url_for('rubrica_avanzada',investigacion_id=c['investigacion_id'],nivel=c['nivel']))


# 12 Comparador de versiones y 26 detector de cambios
@app.route("/innovaciones/investigacion/<int:investigacion_id>/comparar")
@login_requerido
def comparar_entregas(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id): return "Sin permiso",403
    nivel=request.args.get('nivel',1,type=int)
    with conectar_db() as db:
        versiones=db.execute("SELECT * FROM historial_entregas WHERE investigacion_id=? AND nivel=? ORDER BY version DESC",(investigacion_id,nivel)).fetchall()
        obs=db.execute("SELECT * FROM observaciones_puntos WHERE investigacion_id=? AND nivel=? ORDER BY creada_en DESC",(investigacion_id,nivel)).fetchall()
    html=f'<div class="card"><form><label>Nivel</label><select name="nivel">'+''.join(f'<option value="{n}" {"selected" if n==nivel else ""}>Nivel {n}</option>' for n in range(1,7))+'</select><button>Consultar</button></form><h2>Versiones</h2>'
    html+=''.join(f'<p>Versión {v["version"]} · {v["estado"]} · {v["enviado_en"]} · {v["archivo"] or "Sin archivo"}</p>' for v in versiones) or '<p>Sin versiones.</p>'
    html+='</div><div class="card"><h2>Observaciones anteriores</h2>'+''.join(f'<p>{o["texto"]} · {"Corregida" if o["corregida"] else "Pendiente"}</p>' for o in obs)+'</div>'
    if len(versiones)>=2:
        html+=f'<div class="card"><form method="post" action="{url_for("detectar_cambios",investigacion_id=investigacion_id)}"><label>Versión anterior</label><select name="anterior">'+''.join(f'<option value="{v["id"]}">Versión {v["version"]}</option>' for v in versiones)+'</select><label>Versión nueva</label><select name="nueva">'+''.join(f'<option value="{v["id"]}">Versión {v["version"]}</option>' for v in versiones)+'</select><button>Comparar cambios</button></form></div>'
    return html_innovacion("Historial y comparador de correcciones",html)


def extraer_texto_documento(nombre):
    """Extrae texto plano y DOCX; PDF se deja indicado si no hay lector instalado."""
    if not nombre: return ""
    ruta=UPLOAD_DIR/nombre
    if not ruta.exists(): return ""
    ext=ruta.suffix.lower()
    try:
        if ext=='.txt': return ruta.read_text(encoding='utf-8',errors='ignore')
        if ext=='.docx':
            with zipfile.ZipFile(ruta) as z:
                xml=z.read('word/document.xml').decode('utf-8','ignore')
            return re.sub(r'<w:tab[^>]*/>|</w:p>', '\\n', re.sub(r'<[^>]+>',' ',xml))
        if ext=='.odt':
            with zipfile.ZipFile(ruta) as z: xml=z.read('content.xml').decode('utf-8','ignore')
            return re.sub(r'<[^>]+>',' ',xml)
    except Exception:
        return ""
    return ""


@app.route("/innovaciones/investigacion/<int:investigacion_id>/detectar-cambios",methods=["POST"])
@login_requerido
def detectar_cambios(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id): return "Sin permiso",403
    anterior=request.form.get('anterior',type=int); nueva=request.form.get('nueva',type=int)
    with conectar_db() as db:
        a=db.execute("SELECT * FROM historial_entregas WHERE id=? AND investigacion_id=?",(anterior,investigacion_id)).fetchone(); b=db.execute("SELECT * FROM historial_entregas WHERE id=? AND investigacion_id=?",(nueva,investigacion_id)).fetchone()
    if not a or not b or a['nivel']!=b['nivel'] or a['id']==b['id']: return "Selecciona dos versiones diferentes del mismo nivel.",400
    ta=extraer_texto_documento(a['archivo']) or a['texto'] or ''; tb=extraer_texto_documento(b['archivo']) or b['texto'] or ''
    if not ta or not tb: diff="No fue posible extraer texto de uno de los archivos. El comparador automático admite TXT, DOCX y ODT; PDF y otros formatos deben revisarse manualmente."
    else:
        lineas=list(difflib.unified_diff(ta.splitlines(),tb.splitlines(),fromfile=f"Versión {a['version']}",tofile=f"Versión {b['version']}",lineterm=''))
        diff='\n'.join(lineas[:500]) or 'No se encontraron cambios de texto.'
    html='<div class="card"><p>Comparación textual orientativa. No evalúa calidad académica.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+__import__('html').escape(diff)+'</pre></div>'
    return html_innovacion("Cambios entre entregas",html)


# 13 Agenda de tutorías y compromisos
@app.route("/innovaciones/tutor/agenda",methods=["GET","POST"])
@roles_requeridos("admin","tutor")
def agenda_tutor():
    u=usuario_actual()
    with conectar_db() as db:
        if request.method=='POST':
            reunion=request.form.get('reunion_id',type=int); desc=request.form.get('descripcion','').strip(); responsable=request.form.get('responsable_id',type=int) or None; fecha=request.form.get('fecha_limite') or None
            r=db.execute("SELECT sr.id,i.profesor_id FROM solicitudes_reunion sr JOIN investigaciones i ON i.id=sr.investigacion_id WHERE sr.id=?",(reunion,)).fetchone()
            if not r or (u['rol']=='tutor' and r['profesor_id']!=u['id']) or not desc: return "Datos inválidos o sin permiso",400
            db.execute("INSERT INTO compromisos_reunion(reunion_id,descripcion,responsable_id,fecha_limite,creado_por) VALUES(?,?,?,?,?)",(reunion,desc,responsable,fecha,u['id'])); auditar(db,"Agregó compromiso de reunión","reunion",reunion,desc)
        filtro="" if u['rol']=='admin' else "AND i.profesor_id=?"; args=() if u['rol']=='admin' else (u['id'],)
        reuniones=db.execute(f"SELECT sr.*,i.titulo FROM solicitudes_reunion sr JOIN investigaciones i ON i.id=sr.investigacion_id WHERE sr.estado='Aceptada' {filtro} ORDER BY sr.fecha_solicitada DESC",args).fetchall()
        compromisos=db.execute(f"SELECT c.*,sr.fecha_solicitada,sr.hora_solicitada,i.titulo,u.nombre,u.apellido FROM compromisos_reunion c JOIN solicitudes_reunion sr ON sr.id=c.reunion_id JOIN investigaciones i ON i.id=sr.investigacion_id LEFT JOIN usuarios u ON u.id=c.responsable_id WHERE 1=1 {filtro} ORDER BY c.cumplido,c.fecha_limite",args).fetchall()
        miembros=db.execute("SELECT id,nombre,apellido FROM usuarios WHERE rol='estudiante' AND activo=1 ORDER BY apellido").fetchall()
    html='<div class="card"><h2>Registrar acuerdo</h2><form method="post"><label>Reunión</label><select name="reunion_id">'+''.join(f'<option value="{r["id"]}">{r["titulo"]} · {r["fecha_solicitada"]} {r["hora_solicitada"]}</option>' for r in reuniones)+'</select><label>Compromiso</label><input name="descripcion" required><label>Responsable</label><select name="responsable_id"><option value="">Sin asignar</option>'+''.join(f'<option value="{m["id"]}">{m["nombre"]} {m["apellido"]}</option>' for m in miembros)+'</select><label>Fecha límite</label><input type="date" name="fecha_limite"><button>Guardar compromiso</button></form></div><div class="card"><h2>Compromisos</h2>'
    html+=''.join(f'<p><span class="pill {"verde" if c["cumplido"] else "amarillo"}">{"Cumplido" if c["cumplido"] else "Pendiente"}</span> {c["titulo"]} · {c["descripcion"]} · {c["fecha_limite"] or "Sin fecha"}'+(f'<form method="post" action="{url_for("completar_compromiso",compromiso_id=c["id"])}"><button class="secondary">Marcar cumplido</button></form>' if not c["cumplido"] else '')+'</p>' for c in compromisos)+'</div>'
    return html_innovacion("Agenda de tutorías y acuerdos",html)


@app.route("/innovaciones/compromisos/<int:compromiso_id>/completar",methods=["POST"])
@roles_requeridos("admin","tutor")
def completar_compromiso(compromiso_id):
    u=usuario_actual()
    with conectar_db() as db:
        c=db.execute("SELECT c.*,i.profesor_id FROM compromisos_reunion c JOIN solicitudes_reunion sr ON sr.id=c.reunion_id JOIN investigaciones i ON i.id=sr.investigacion_id WHERE c.id=?",(compromiso_id,)).fetchone()
        if not c or (u['rol']=='tutor' and c['profesor_id']!=u['id']): return "Sin permiso",403
        db.execute("UPDATE compromisos_reunion SET cumplido=1 WHERE id=?",(compromiso_id,)); auditar(db,"Marcó compromiso cumplido","compromiso",compromiso_id)
    return redirect(url_for('agenda_tutor'))





# ============================================================
# 14. REVISOR DE ESTRUCTURA Y CITAS (ORIENTATIVO)
# ============================================================

@app.route(
    "/innovaciones/investigacion/<int:investigacion_id>/revisor"
)
@roles_requeridos("admin", "tutor")
def revisor_academico(investigacion_id):

    usuario = usuario_actual()

    # Verificar acceso del tutor.
    if usuario["rol"] == "tutor":
        if not exigir_acceso_investigacion(
            usuario,
            investigacion_id
        ):
            return "Sin permiso", 403

    with conectar_db() as db:

        # Obtener checklist académico.
        items = db.execute(
            """
            SELECT *
            FROM checklist_academico
            WHERE investigacion_id = ?
            """,
            (investigacion_id,)
        ).fetchall()

        # Obtener última entrega.
        ultima_entrega = db.execute(
            """
            SELECT archivo, texto
            FROM entregas
            WHERE investigacion_id = ?
            ORDER BY nivel DESC
            LIMIT 1
            """,
            (investigacion_id,)
        ).fetchone()

        # Obtener investigación.
        investigacion = db.execute(
            """
            SELECT id, titulo
            FROM investigaciones
            WHERE id = ?
            """,
            (investigacion_id,)
        ).fetchone()

    documentos = db.execute(
        """
        SELECT id, archivo, nivel, version
        FROM historial_entregas
        WHERE investigacion_id = ?
        ORDER BY nivel DESC, version DESC
        """,
        (investigacion_id,)
    ).fetchall()

    if not investigacion:
        return "Investigación no encontrada", 404

    # Extraer texto.
    texto = ""

    if ultima_entrega:

        if ultima_entrega["archivo"]:
            texto = (
                extraer_texto_documento(
                    ultima_entrega["archivo"]
                ) or ""
            )

        if not texto:
            texto = ultima_entrega["texto"] or ""

    avisos = []

    if texto:

        texto_minusculas = texto.lower()

        apartados = [
            "planteamiento del problema",
            "objetivo",
            "justificación",
            "metodología",
            "conclusiones",
            "referencias",
            "bibliografía"
        ]

        for apartado in apartados:

            if apartado not in texto_minusculas:
                avisos.append(
                    "No se encontró el apartado: "
                    + apartado
                )

        # Comprobar citas autor-año.
        patron_citas = (
            r"\([^)]*\b(?:19|20)\d{2}\b[^)]*\)"
        )

        if not re.search(patron_citas, texto):
            avisos.append(
                "No se detectaron posibles citas APA "
                "con el patrón básico (Autor, 2022)."
            )

        # Comprobar enlaces o DOI.
        if not re.search(
            r"https?://|doi\.org",
            texto,
            re.IGNORECASE
        ):
            avisos.append(
                "No se detectaron URL o DOI visibles."
            )

        # Comprobar dobles espacios.
        if re.search(r" {2,}", texto):
            avisos.append(
                "Se detectaron posibles espacios dobles."
            )

    else:

        avisos.append(
            "No se pudo extraer texto de la entrega. "
            "Revisa el documento directamente."
        )

    # --------------------------------------------------------
    # DOCUMENTOS DE LA IZQUIERDA
    # --------------------------------------------------------

    html_documentos = ""

    for documento in documentos:

        nombre = documento["archivo"] or "Documento sin nombre"
        
        html_documentos += f"""
            <div class="revisor-documento">
                <span class="revisor-icono">📄</span>

                <div class="revisor-documento-info">
                    <strong>{nombre}</strong>
                    <small>
                        Nivel {documento["nivel"]}
                        · Versión {documento["version"]}
                    </small>
                </div>
            </div>
        """

    if not html_documentos:

        html_documentos = """
            <p class="revisor-vacio">
                Todavía no hay documentos registrados.
            </p>
        """

    # --------------------------------------------------------
    # RESULTADO DE LA DERECHA
    # --------------------------------------------------------

    criterios = [
        "Planteamiento del problema",
        "Objetivos",
        "Justificación",
        "Metodología",
        "Conclusiones",
        "Citas en formato APA (Autor, año)",
        "Referencias o bibliografía",
        "Formato sin espacios dobles"
    ]

    texto_busqueda = texto.lower()

    comprobaciones = [
        "planteamiento del problema" in texto_busqueda,
        "objetivo" in texto_busqueda,
        "justificación" in texto_busqueda,
        "metodología" in texto_busqueda,
        "conclusiones" in texto_busqueda,
        bool(re.search(
            r"\([^)]*\b(?:19|20)\d{2}\b[^)]*\)",
            texto
        )),
        (
            "referencias" in texto_busqueda
            or "bibliografía" in texto_busqueda
        ),
        not bool(re.search(r" {2,}", texto))
    ]

    cumplidos = sum(comprobaciones)
    porcentaje = round((cumplidos / len(criterios)) * 100)

    html_criterios = ""

    for criterio, cumple in zip(
        criterios,
        comprobaciones
    ):

        icono = "✓" if cumple else "!"
        clase = "cumplido" if cumple else "pendiente"

        html_criterios += f"""
            <div class="revisor-criterio">
                <span class="revisor-estado {clase}">
                    {icono}
                </span>

                <span>{criterio}</span>
            </div>
        """

    # --------------------------------------------------------
    # ALERTAS
    # --------------------------------------------------------

    html_avisos = ""

    for aviso in avisos:

        html_avisos += f"""
            <div class="revisor-aviso">
                <span>⚠️</span>
                <p>{aviso}</p>
            </div>
        """

    if not html_avisos:

        html_avisos = """
            <p class="revisor-vacio">
                No se encontraron alertas básicas.
            </p>
        """

    # --------------------------------------------------------
    # CONTENIDO HTML
    # --------------------------------------------------------

    html = f"""
        <style>

            .revisor-contenedor {{
                width: 100%;
            }}

            .revisor-titulo {{
                margin: 0 0 8px;
                color: #17365f;
                font-size: 25px;
                font-weight: 800;
            }}

            .revisor-descripcion {{
                margin: 0 0 22px;
                color: #64748b;
                font-size: 13px;
                line-height: 1.7;
            }}

            .revisor-distribucion {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 22px;
                align-items: start;
            }}

            .revisor-card {{
                min-width: 0;
                padding: 22px;
                border: 1px solid #e1e8f0;
                border-radius: 14px;
                background: #ffffff;
                box-shadow: 0 4px 14px rgba(20,40,70,0.04);
            }}

            .revisor-card h2 {{
                margin: 0 0 8px;
                color: #17365f;
                font-size: 19px;
            }}

            .revisor-subtitulo {{
                margin: 0 0 18px;
                color: #64748b;
                font-size: 12px;
                line-height: 1.6;
            }}

            .revisor-documentos {{
                display: flex;
                flex-direction: column;
                gap: 10px;
            }}

            .revisor-documento {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 13px;
                border: 1px solid #e8edf4;
                border-radius: 10px;
                background: #ffffff;
            }}

            .revisor-icono {{
                font-size: 21px;
            }}

            .revisor-documento-info {{
                display: flex;
                flex-direction: column;
                gap: 5px;
                min-width: 0;
            }}

            .revisor-documento-info strong {{
                color: #334155;
                font-size: 12px;
                overflow-wrap: anywhere;
            }}

            .revisor-documento-info small {{
                color: #94a3b8;
                font-size: 11px;
            }}

            .revisor-puntaje {{
                margin: 15px 0;
                color: #16a34a;
                font-size: 34px;
                font-weight: 800;
            }}

            .revisor-barra {{
                width: 100%;
                height: 8px;
                overflow: hidden;
                border-radius: 20px;
                background: #e2e8f0;
                margin-bottom: 20px;
            }}

            .revisor-barra-progreso {{
                height: 100%;
                width: {porcentaje}%;
                border-radius: 20px;
                background: #16a34a;
            }}

            .revisor-criterios {{
                display: flex;
                flex-direction: column;
                gap: 13px;
            }}

            .revisor-criterio {{
                display: flex;
                align-items: flex-start;
                gap: 10px;
                color: #334155;
                font-size: 12px;
                line-height: 1.5;
            }}

            .revisor-estado {{
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                width: 21px;
                height: 21px;
                border-radius: 50%;
                font-weight: 800;
            }}

            .revisor-estado.cumplido {{
                background: #dcfce7;
                color: #166534;
            }}

            .revisor-estado.pendiente {{
                background: #fef3c7;
                color: #92400e;
            }}

            .revisor-alertas {{
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-top: 20px;
            }}

            .revisor-aviso {{
                display: flex;
                gap: 10px;
                padding: 12px;
                border: 1px solid #f3dfaa;
                border-radius: 9px;
                background: #fffbeb;
                color: #854d0e;
                font-size: 12px;
                line-height: 1.6;
            }}

            .revisor-aviso p {{
                margin: 0;
            }}

            .revisor-nota {{
                margin-top: 18px;
                padding: 12px;
                border-radius: 9px;
                background: #eff6ff;
                color: #1e40af;
                font-size: 11px;
                line-height: 1.6;
            }}

            .revisor-vacio {{
                color: #94a3b8;
                font-size: 12px;
            }}

            @media (max-width: 750px) {{
                .revisor-distribucion {{
                    grid-template-columns: 1fr;
                }}
            }}

        </style>

        <div class="revisor-contenedor">

            <h1 class="revisor-titulo">
                Revisor de estructura académica
            </h1>

            <p class="revisor-descripcion">
                Revisión rápida de la forma del trabajo para
                que tu tiempo vaya al contenido.
            </p>

            <div class="revisor-distribucion">

                <!-- COLUMNA IZQUIERDA -->

                <section class="revisor-card">

                    <h2>📄 Texto a revisar</h2>

                    <p class="revisor-subtitulo">
                        {investigacion["titulo"]}
                    </p>

                    <div class="revisor-documentos">
                        {html_documentos}
                    </div>

                </section>

                <!-- COLUMNA DERECHA -->

                <section class="revisor-card">

                    <h2>📊 Resultado</h2>

                    <div class="revisor-puntaje">
                        {cumplidos} de 8
                    </div>

                    <div class="revisor-barra">
                        <div class="revisor-barra-progreso"></div>
                    </div>

                    <div class="revisor-criterios">
                        {html_criterios}
                    </div>

                    <div class="revisor-alertas">
                        {html_avisos}
                    </div>

                    <div class="revisor-nota">
                        El revisor busca apartados y citas en el texto.
                        Es una ayuda orientativa: no mide la calidad
                        del contenido ni detecta copias.
                    </div>

                </section>

            </div>

        </div>
    """

    return html_innovacion(
        "Revisor de estructura académica",
        html
    )




@app.route("/innovaciones/admin/auditoria")
@roles_requeridos("admin")
def registro_auditoria():

    usuario_filtro = request.args.get("usuario", "").strip()
    accion_filtro = request.args.get("accion", "").strip()

    # Verificar integridad de los registros.
    verificacion = verificar_integridad_auditoria()

    with conectar_db() as db:

        # Obtener usuarios que tienen actividad.
        personas = db.execute("""
            SELECT DISTINCT
                u.id,
                u.nombre,
                u.apellido
            FROM auditoria_tesislab a
            LEFT JOIN usuarios u
                ON u.id = a.usuario_id
            WHERE u.id IS NOT NULL
            ORDER BY u.nombre, u.apellido
        """).fetchall()

        # Obtener tipos de acciones.
        acciones = db.execute("""
            SELECT DISTINCT accion
            FROM auditoria_tesislab
            ORDER BY accion
        """).fetchall()

        # Construir filtros.
        condiciones = []
        parametros = []

        if usuario_filtro.isdigit():
            condiciones.append("a.usuario_id = ?")
            parametros.append(int(usuario_filtro))

        if accion_filtro:
            condiciones.append("a.accion = ?")
            parametros.append(accion_filtro)

        where = (
            "WHERE " + " AND ".join(condiciones)
            if condiciones
            else ""
        )

        # Obtener historial.
        registros = db.execute(f"""
            SELECT
                a.*,
                u.nombre,
                u.apellido,
                u.usuario
            FROM auditoria_tesislab a
            LEFT JOIN usuarios u
                ON u.id = a.usuario_id
            {where}
            ORDER BY a.id DESC
            LIMIT 300
        """, parametros).fetchall()

    # Estado de seguridad.
    if verificacion["integro"]:

        estado_html = """
            <div class="auditoria-estado auditoria-ok">
                <div class="auditoria-icono">✓</div>
                <div>
                    <strong>Registro íntegro</strong>
                    <p>No se detectaron alteraciones en los registros sellados.</p>
                </div>
            </div>
        """

    else:

        estado_html = f"""
            <div class="auditoria-estado auditoria-error">
                <div class="auditoria-icono">!</div>
                <div>
                    <strong>Alteración detectada</strong>
                    <p>
                        Se encontraron
                        {len(verificacion["alteraciones"])}
                        inconsistencias.
                    </p>
                </div>
            </div>
        """

    # Opciones de usuarios.
    opciones_personas = """
        <option value="">Todas las personas</option>
    """

    for persona in personas:

        nombre = (
            f'{persona["nombre"] or ""} '
            f'{persona["apellido"] or ""}'
        ).strip()

        seleccionado = (
            "selected"
            if usuario_filtro == str(persona["id"])
            else ""
        )

        opciones_personas += f"""
            <option value="{persona["id"]}" {seleccionado}>
                {escape(nombre)}
            </option>
        """

    # Opciones de acciones.
    opciones_acciones = """
        <option value="">Todas las acciones</option>
    """

    for accion in acciones:

        seleccionado = (
            "selected"
            if accion_filtro == accion["accion"]
            else ""
        )

        opciones_acciones += f"""
            <option value="{escape(accion["accion"])}" {seleccionado}>
                {escape(accion["accion"])}
            </option>
        """

    # Historial de actividad.
    historial_html = ""

    for registro in registros:

        nombre = (
            f'{registro["nombre"] or ""} '
            f'{registro["apellido"] or ""}'
        ).strip()

        if not nombre:
            nombre = registro["usuario"] or "Cuenta eliminada"

        hash_actual = registro["hash_actual"]

        sello = (
            hash_actual[:12]
            if hash_actual
            else "Sin sello histórico"
        )

        historial_html += f"""
            <div class="auditoria-item">
                <div class="auditoria-punto"></div>

                <div class="auditoria-contenido">
                    <div class="auditoria-item-superior">
                        <strong>
                            {escape(registro["accion"])}
                        </strong>

                        <span class="auditoria-sello">
                            #{escape(sello)}
                        </span>
                    </div>

                    <p class="auditoria-detalle">
                        {escape(
                            registro["detalle"]
                            or registro["entidad"]
                        )}
                    </p>

                    <div class="auditoria-metadata">
                        <span>{escape(registro["creado_en"])}</span>
                        <span>·</span>
                        <span>{escape(nombre)}</span>
                    </div>
                </div>
            </div>
        """

    if not historial_html:

        historial_html = """
            <div class="auditoria-vacio">
                No hay registros de actividad para mostrar.
            </div>
        """

    # Mensajes de confirmación.
    mensajes_html = ""

    for categoria, mensaje in get_flashed_messages(with_categories=True):

        color = (
            "#166534"
            if categoria == "success"
            else "#b91c1c"
        )

        fondo = (
            "#ecfdf3"
            if categoria == "success"
            else "#fef2f2"
        )

        mensajes_html += f"""
            <div style="
                padding: 13px;
                margin-bottom: 15px;
                border-radius: 9px;
                background: {fondo};
                color: {color};
            ">
                {escape(mensaje)}
            </div>
        """

    # Diseño de la página.
    html = f"""

        <style>

            .auditoria-page {{
                max-width: 1150px;
                margin: 0 auto;
                padding: 25px 20px 45px;
                color: #172b4d;
            }}

            .auditoria-etiqueta {{
                color: #2563a6;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1.5px;
            }}

            .auditoria-page h1 {{
                font-size: 30px;
                margin: 8px 0;
            }}

            .auditoria-descripcion {{
                color: #64748b;
                margin-bottom: 25px;
            }}

            .auditoria-estado {{
                display: flex;
                align-items: center;
                gap: 15px;
                padding: 20px;
                border-radius: 14px;
                margin-bottom: 20px;
            }}

            .auditoria-ok {{
                background: #ecfdf3;
                border: 1px solid #bbf7d0;
            }}

            .auditoria-error {{
                background: #fff1f2;
                border: 1px solid #fecdd3;
            }}

            .auditoria-icono {{
                width: 42px;
                height: 42px;
                display: grid;
                place-items: center;
                border-radius: 50%;
                background: white;
                font-size: 23px;
                font-weight: bold;
            }}

            .auditoria-ok .auditoria-icono {{
                color: #15803d;
            }}

            .auditoria-error .auditoria-icono {{
                color: #dc2626;
            }}

            .auditoria-estado p {{
                margin: 5px 0 0;
                font-size: 13px;
                color: #64748b;
            }}

            .auditoria-prueba {{
                margin-bottom: 20px;
            }}

            .auditoria-prueba button {{
                padding: 12px 18px;
                border: none;
                border-radius: 9px;
                background: #1d4ed8;
                color: white;
                font-weight: 700;
                cursor: pointer;
            }}

            .auditoria-prueba button:hover {{
                background: #1e40af;
            }}

            .auditoria-resumen {{
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                margin-bottom: 20px;
            }}

            .auditoria-resumen div {{
                background: white;
                border: 1px solid #e2e8f0;
                padding: 13px 18px;
                border-radius: 12px;
                font-size: 13px;
            }}

            .auditoria-resumen strong {{
                display: block;
                font-size: 20px;
                color: #1d4ed8;
            }}

            .auditoria-filtros {{
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                padding: 18px;
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                margin-bottom: 22px;
            }}

            .auditoria-filtros select {{
                flex: 1;
                min-width: 190px;
                padding: 12px;
                border: 1px solid #cbd5e1;
                border-radius: 9px;
                background: white;
            }}

            .auditoria-filtros button {{
                padding: 11px 20px;
                border: none;
                border-radius: 9px;
                background: #1d4ed8;
                color: white;
                font-weight: 700;
                cursor: pointer;
            }}

            .auditoria-lista {{
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                padding: 22px;
            }}

            .auditoria-lista h2 {{
                font-size: 18px;
                margin: 0 0 22px;
            }}

            .auditoria-item {{
                display: flex;
                gap: 15px;
                position: relative;
                padding-bottom: 25px;
            }}

            .auditoria-punto {{
                width: 11px;
                height: 11px;
                min-width: 11px;
                margin-top: 5px;
                border-radius: 50%;
                background: #2563eb;
                position: relative;
                z-index: 1;
            }}

            .auditoria-item:not(:last-child)::before {{
                content: "";
                position: absolute;
                left: 5px;
                top: 15px;
                bottom: 0;
                width: 1px;
                background: #dbeafe;
            }}

            .auditoria-contenido {{
                flex: 1;
                min-width: 0;
            }}

            .auditoria-item-superior {{
                display: flex;
                justify-content: space-between;
                gap: 12px;
                flex-wrap: wrap;
            }}

            .auditoria-sello {{
                color: #2563eb;
                background: #eff6ff;
                padding: 4px 9px;
                border-radius: 6px;
                font-family: monospace;
                font-size: 12px;
            }}

            .auditoria-detalle {{
                margin: 8px 0;
                color: #475569;
                font-size: 14px;
                overflow-wrap: anywhere;
            }}

            .auditoria-metadata {{
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                color: #94a3b8;
                font-size: 12px;
            }}

            .auditoria-vacio {{
                padding: 25px;
                text-align: center;
                color: #64748b;
            }}

            .auditoria-nota {{
                margin-top: 18px;
                color: #64748b;
                font-size: 13px;
                line-height: 1.6;
            }}

        </style>

        <div class="auditoria-page">

            <span class="auditoria-etiqueta">
                CONTROL INSTITUCIONAL
            </span>

            <h1>Registro de actividad</h1>

            <p class="auditoria-descripcion">
                Cada acción importante queda anotada con fecha,
                persona y un sello de seguridad.
            </p>

            {estado_html}

            {mensajes_html}

            <form
                method="POST"
                action="{url_for('probar_integridad_auditoria')}"
                class="auditoria-prueba"
            >
                <button type="submit">
                    Probar: alterar un registro
                </button>
            </form>

            <div class="auditoria-resumen">

                <div>
                    <strong>{verificacion["total_verificados"]}</strong>
                    Registros verificados
                </div>

                <div>
                    <strong>{verificacion["registros_antiguos"]}</strong>
                    Registros históricos sin sello
                </div>

                <div>
                    <strong>{len(verificacion["alteraciones"])}</strong>
                    Inconsistencias detectadas
                </div>

            </div>

            <form method="GET" class="auditoria-filtros">

                <select name="usuario">
                    {opciones_personas}
                </select>

                <select name="accion">
                    {opciones_acciones}
                </select>

                <button type="submit">
                    Filtrar
                </button>

                <a href="{url_for('registro_auditoria')}">
                    Limpiar
                </a>

            </form>

            <div class="auditoria-lista">

                <h2>Historial de actividad</h2>

                {historial_html}

            </div>

            <p class="auditoria-nota">
                Cada sello se calcula con los datos del registro
                y el sello anterior. Si alguien modifica un dato,
                el sistema puede detectar la alteración.
            </p>

        </div>
    """

    return html_innovacion(
        "Registro de actividad",
        html
    )




# 17-24 Administración
@app.route("/innovaciones/admin")
@roles_requeridos("admin")
def innovaciones_admin():
    with conectar_db() as db:
        usuarios=db.execute("SELECT rol,COUNT(*) total FROM usuarios WHERE activo=1 GROUP BY rol").fetchall()
        inv=db.execute("SELECT COUNT(*) total,SUM(CASE WHEN finalizada=1 THEN 1 ELSE 0 END) finalizadas,SUM(CASE WHEN estado='Correcciones pendientes' THEN 1 ELSE 0 END) riesgos FROM investigaciones").fetchone()
        atrasados=db.execute("SELECT COUNT(*) FROM investigaciones i WHERE i.finalizada=0 AND EXISTS(SELECT 1 FROM niveles_investigacion n WHERE n.investigacion_id=i.id AND n.estado='Necesita correcciones')").fetchone()[0]
    counts={r['rol']:r['total'] for r in usuarios}
    html=f'<div class="grid">'+''.join(f'<div class="card"><h2>{v or 0}</h2><p>{k}</p></div>' for k,v in [("Estudiantes",counts.get('estudiante',0)),("Tutores",counts.get('tutor',0)),("Administradores",counts.get('admin',0)),("Investigaciones",inv['total'] or 0),("Finalizadas",inv['finalizadas'] or 0),("Con correcciones",atrasados)])+'</div><div class="grid">'
    for label,endpoint in [("Distribución de tutores","carga_tutores"),("Mapa de riesgos","mapa_riesgos"),("Informes automáticos","informe_institucional"),("Registro de actividad","registro_auditoria"),("Archivo histórico","archivo_historico"),("Comunicados","comunicados_admin"),("Copias de respaldo","respaldo_datos")]: html+=f'<div class="card"><h2>{label}</h2><a class="btn" href="{url_for(endpoint)}">Abrir</a></div>'
    html+='</div>'
    return html_innovacion("Centro de control institucional",html)


@app.route("/innovaciones/admin/carga-tutores")
@roles_requeridos("admin")
def carga_tutores():
    with conectar_db() as db:
        rows=db.execute("SELECT u.id,u.nombre,u.apellido,COUNT(i.id) proyectos FROM usuarios u LEFT JOIN investigaciones i ON i.profesor_id=u.id AND i.finalizada=0 WHERE u.rol='tutor' AND u.activo=1 GROUP BY u.id ORDER BY proyectos,u.apellido").fetchall()
    html='<div class="card"><table><tr><th>Tutor</th><th>Proyectos activos</th><th>Distribución</th></tr>'
    for r in rows: html+=f'<tr><td>{r["nombre"]} {r["apellido"]}</td><td>{r["proyectos"]}</td><td><div class="barra"><span style="width:{min(100,r["proyectos"]*10)}%"></span></div></td></tr>'
    html+='</table><p class="muted">La vista ayuda a equilibrar asignaciones; no cambia tutores automáticamente.</p></div>'
    return html_innovacion("Distribución equilibrada de tutores",html)


@app.route("/innovaciones/admin/riesgos")
@roles_requeridos("admin")
def mapa_riesgos():
    with conectar_db() as db:
        rows=db.execute("""SELECT i.id,i.titulo,i.estado,g.nombre grupo,t.nombre tutor, (SELECT COUNT(*) FROM observaciones_puntos o WHERE o.investigacion_id=i.id AND o.corregida=0) obs,(SELECT COUNT(*) FROM historial_entregas h WHERE h.investigacion_id=i.id) versiones,(SELECT MAX(h.enviado_en) FROM historial_entregas h WHERE h.investigacion_id=i.id) ultima FROM investigaciones i JOIN grupos g ON g.id=i.grupo_id LEFT JOIN usuarios t ON t.id=i.profesor_id WHERE i.finalizada=0 ORDER BY obs DESC,ultima ASC""").fetchall()
    html='<div class="card"><p>Las alertas sirven para ofrecer acompañamiento, no para etiquetar estudiantes.</p><table><tr><th>Grupo</th><th>Estado</th><th>Observaciones abiertas</th><th>Actividad</th><th>Alerta</th></tr>'
    for r in rows:
        alerta='Revisar acompañamiento' if r['obs']>=4 or not r['ultima'] else ('Verificar inactividad' if r['ultima'][:10] < (date.today()-timedelta(days=21)).isoformat() else 'Seguimiento normal')
        html+=f'<tr><td>{r["grupo"]} · {r["titulo"]}</td><td>{r["estado"]}</td><td>{r["obs"]}</td><td>{r["ultima"] or "Sin entregas"}</td><td>{alerta}</td></tr>'
    html+='</table></div>'
    return html_innovacion("Mapa de riesgos académicos",html)


@app.route("/innovaciones/admin/informe")
@roles_requeridos("admin")
def informe_institucional():
    curso=request.args.get('curso','').strip(); area=request.args.get('area','').strip(); tutor=request.args.get('tutor',type=int)
    where=[]; args=[]
    if curso: where.append('u.curso=?'); args.append(curso)
    if area: where.append('i.area_principal=?'); args.append(area)
    if tutor: where.append('i.profesor_id=?'); args.append(tutor)
    clause=('WHERE '+' AND '.join(where)) if where else ''
    with conectar_db() as db:
        rows=db.execute(f"""SELECT i.id,i.titulo,i.estado,i.nota_final,i.finalizada,i.area_principal,g.nombre grupo,t.nombre tutor_nombre,t.apellido tutor_apellido,COUNT(DISTINCT mg.estudiante_id) alumnos FROM investigaciones i JOIN grupos g ON g.id=i.grupo_id LEFT JOIN usuarios t ON t.id=i.profesor_id LEFT JOIN miembros_grupo mg ON mg.grupo_id=g.id AND mg.estado='activo' LEFT JOIN usuarios u ON u.id=mg.estudiante_id {clause} GROUP BY i.id ORDER BY i.creado_en DESC""",args).fetchall()
        tutores=db.execute("SELECT id,nombre,apellido FROM usuarios WHERE rol='tutor' AND activo=1").fetchall()
    html='<div class="card"><form><label>Curso</label><input name="curso" value="'+curso+'"><label>Área</label><input name="area" value="'+area+'"><label>Tutor ID (opcional)</label><input type="number" name="tutor" value="'+(str(tutor) if tutor else '')+'"><button>Filtrar</button> <a class="btn secondary" href="'+url_for('exportar_informe',curso=curso,area=area,tutor=tutor or '')+'">Descargar CSV</a></form></div><div class="card"><table><tr><th>Investigación</th><th>Grupo</th><th>Tutor</th><th>Alumnos</th><th>Estado</th><th>Nota</th></tr>'
    for r in rows: html+=f'<tr><td>{r["titulo"]}</td><td>{r["grupo"]}</td><td>{r["tutor_nombre"] or "Sin asignar"} {r["tutor_apellido"] or ""}</td><td>{r["alumnos"]}</td><td>{r["estado"]}</td><td>{r["nota_final"] if r["nota_final"] is not None else "—"}</td></tr>'
    html+='</table></div>'
    return html_innovacion("Informes institucionales",html)


@app.route("/innovaciones/admin/informe.csv")
@roles_requeridos("admin")
def exportar_informe():

    curso = request.args.get("curso", "").strip()
    area = request.args.get("area", "").strip()
    tutor = request.args.get("tutor", type=int)

    where = []
    args = []

    if curso:
        where.append("u.curso = ?")
        args.append(curso)

    if area:
        where.append("i.area_principal = ?")
        args.append(area)

    if tutor:
        where.append("i.profesor_id = ?")
        args.append(tutor)

    clause = (
        "WHERE " + " AND ".join(where)
        if where else ""
    )

    with conectar_db() as db:

        rows = db.execute(
            f"""
            SELECT
                i.id,
                i.titulo,
                i.estado,
                i.nota_final,
                i.finalizada,
                i.area_principal,
                g.nombre AS grupo,
                t.nombre AS tutor,
                u.curso

            FROM investigaciones i

            JOIN grupos g
                ON g.id = i.grupo_id

            LEFT JOIN usuarios t
                ON t.id = i.profesor_id

            LEFT JOIN miembros_grupo mg
                ON mg.grupo_id = g.id
                AND mg.estado = 'activo'

            LEFT JOIN usuarios u
                ON u.id = mg.estudiante_id

            {clause}

            GROUP BY i.id
            """,
            args
        ).fetchall()

    out = io.StringIO()
    w = csv.writer(out)

    w.writerow([
        "ID",
        "Investigación",
        "Grupo",
        "Tutor",
        "Curso",
        "Área",
        "Estado",
        "Nota",
        "Finalizada"
    ])

    for r in rows:

        w.writerow([
            r["id"],
            r["titulo"],
            r["grupo"],
            r["tutor"],
            r["curso"],
            r["area_principal"],
            r["estado"],
            r["nota_final"],
            r["finalizada"]
        ])

    resp = make_response("\ufeff" + out.getvalue())

    resp.headers["Content-Type"] = "text/csv; charset=utf-8"

    resp.headers["Content-Disposition"] = (
        "attachment; filename=informe_tesis_lab.csv"
    )

    return resp

@app.route("/innovaciones/admin/archivo-historico")
@roles_requeridos("admin","tutor")
def archivo_historico():
    q=request.args.get('q','').strip(); area=request.args.get('area','').strip()
    sql="SELECT i.id,i.titulo,i.descripcion,i.area_principal,i.subarea,i.nota_final,i.finalizada,g.nombre grupo FROM investigaciones i JOIN grupos g ON g.id=i.grupo_id WHERE i.finalizada=1";args=[]
    if q:sql+=" AND (i.titulo LIKE ? OR i.descripcion LIKE ?)";args += [f'%{q}%',f'%{q}%']
    if area:sql+=" AND i.area_principal=?";args.append(area)
    sql+=" ORDER BY i.creado_en DESC"
    with conectar_db() as db:rows=db.execute(sql,args).fetchall()
    html=f'<div class="card"><form><label>Buscar</label><input name="q" value="{q}"><label>Área</label><input name="area" value="{area}"><button>Buscar</button></form></div><div class="card"><h2>Trabajos finalizados</h2>'
    for r in rows:html+=f'<p><b>{r["titulo"]}</b> · {r["grupo"]} · {r["area_principal"]}/{r["subarea"]} · Nota {r["nota_final"] if r["nota_final"] is not None else "No publicada"}</p>'
    html+='</div>'
    return html_innovacion("Archivo histórico de investigaciones",html)



# ============================================================
# ADMINISTRAR COMUNICADOS INSTITUCIONALES
# ============================================================

@app.route(
    "/innovaciones/admin/comunicados",
    methods=["GET", "POST"]
)
@roles_requeridos("admin")
def comunicados_admin():

    u = usuario_actual()

    with conectar_db() as db:

        # PUBLICAR NUEVO COMUNICADO

        if request.method == "POST":

            titulo = request.form.get(
                "titulo", ""
            ).strip()

            contenido = request.form.get(
                "contenido", ""
            ).strip()

            dest = request.form.get(
                "destinatario", "todos"
            )

            curso = request.form.get(
                "curso", ""
            ).strip() or None

            if (
                not titulo
                or not contenido
                or dest not in (
                    "todos",
                    "tutores",
                    "estudiantes",
                    "curso"
                )
            ):

                flash(
                    "Completa los campos del comunicado.",
                    "error"
                )

            else:

                cur = db.execute("""
                    INSERT INTO comunicados_institucionales (
                        titulo,
                        contenido,
                        destinatario,
                        curso,
                        publicado_por
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    titulo,
                    contenido,
                    dest,
                    curso,
                    u["id"]
                ))

                auditar(
                    db,
                    "Publicó comunicado",
                    "comunicado",
                    cur.lastrowid,
                    titulo
                )

                flash(
                    "Comunicado publicado.",
                    "exito"
                )

        # OBTENER COMUNICADOS PUBLICADOS

        rows = db.execute("""
            SELECT
                c.*,
                u.nombre,
                u.apellido,

                (
                    SELECT COUNT(*)
                    FROM lecturas_comunicados AS l
                    WHERE l.comunicado_id = c.id
                ) AS lecturas

            FROM comunicados_institucionales AS c

            JOIN usuarios AS u
                ON u.id = c.publicado_por

            ORDER BY c.publicado_en DESC

        """).fetchall()

    # INTERFAZ DE ADMINISTRACIÓN

    html = """
        <div class="card">

            <h2>Nuevo comunicado</h2>

            <form method="post">

                <label>Título</label>

                <input
                    name="titulo"
                    required
                >

                <label>Contenido</label>

                <textarea
                    name="contenido"
                    required
                ></textarea>

                <label>Destinatarios</label>

                <select name="destinatario">

                    <option value="todos">
                        Todos
                    </option>

                    <option value="tutores">
                        Tutores
                    </option>

                    <option value="estudiantes">
                        Estudiantes
                    </option>

                    <option value="curso">
                        Curso específico
                    </option>

                </select>

                <label>Curso</label>

                <input name="curso">

                <button type="submit">
                    Publicar
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Publicados</h2>

    """

    html += "".join(
        f"""
            <p>
                <b>{r['titulo']}</b>
                · {r['publicado_en']}
                · {r['lecturas']} lecturas
            </p>
        """
        for r in rows
    )

    html += """
        </div>
    """

    return html_innovacion(
        "Comunicados institucionales",
        html
    )


# ============================================================
# VER COMUNICADOS INSTITUCIONALES
# ============================================================

@app.route(
    "/innovaciones/comunicados"
)
@login_requerido
def ver_comunicados():

    u = usuario_actual()

    with conectar_db() as db:

        # OBTENER COMUNICADOS SEGÚN EL DESTINATARIO

        rows = db.execute("""
            SELECT
                c.*,

                EXISTS (
                    SELECT 1
                    FROM lecturas_comunicados AS l
                    WHERE l.comunicado_id = c.id
                      AND l.usuario_id = ?
                ) AS leido

            FROM comunicados_institucionales AS c

            WHERE c.activo = 1

              AND (
                    c.destinatario = 'todos'

                    OR (
                        c.destinatario = 'tutores'
                        AND ? = 'tutor'
                    )

                    OR (
                        c.destinatario = 'estudiantes'
                        AND ? = 'estudiante'
                    )

                    OR (
                        c.destinatario = 'curso'
                        AND ? = 'estudiante'
                        AND c.curso = ?
                    )
              )

            ORDER BY c.publicado_en DESC

        """, (
            u["id"],
            u["rol"],
            u["rol"],
            u["rol"],
            u["curso"] or ""
        )).fetchall()

    # CONSTRUIR INTERFAZ DE COMUNICADOS

    html = ""

    for r in rows:

        html += f"""
            <div class="card">

                <h2>
                    {r['titulo']}
                </h2>

                <p>
                    {r['contenido']}
                </p>

                <p class="muted">
                    {r['publicado_en']}
                </p>
        """

        if not r["leido"]:

            html += f"""
                <form
                    method="post"
                    action="{url_for(
                        'leer_comunicado',
                        comunicado_id=r['id']
                    )}"
                >

                    <button type="submit">
                        Confirmar lectura
                    </button>

                </form>
            """

        else:

            html += """
                <span class="pill verde">
                    Leído
                </span>
            """

        html += """
            </div>
        """

    if not rows:

        html = """
            <div class="card">
                No hay comunicados para tu cuenta.
            </div>
        """

    return html_innovacion(
        "Comunicados",
        html
    )


# ============================================================
# LEER COMUNICADO
# ============================================================

@app.route(
    "/innovaciones/comunicados/<int:comunicado_id>/leer",
    methods=["POST"]
)
@login_requerido
def leer_comunicado(comunicado_id):

    u = usuario_actual()

    with conectar_db() as db:

        db.execute("""
            INSERT OR IGNORE INTO lecturas_comunicados (
                comunicado_id,
                usuario_id
            )
            VALUES (?, ?)
        """, (
            comunicado_id,
            u["id"]
        ))

    return redirect(
        url_for("ver_comunicados")
    )


# ============================================================
# SEGURIDAD Y COPIAS DE RESPALDO
# ============================================================

@app.route(
    "/innovaciones/admin/respaldo",
    methods=["GET", "POST"]
)
@roles_requeridos("admin")
def respaldo_datos():

    # ========================================================
    # GENERAR RESPALDO
    # ========================================================

    if request.method == "POST":

        nombre = (
            f"respaldo_tesis_lab_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )

        destino = BASE_DIR / "backups"

        destino.mkdir(exist_ok=True)

        ruta = destino / nombre

        # VERIFICAR INTEGRIDAD DE LA BASE DE DATOS

        with conectar_db() as db:

            integrity = db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if integrity != "ok":

                return (
                    f"La base de datos no superó "
                    f"integrity_check: {integrity}",
                    500
                )

            db.execute(
                "PRAGMA wal_checkpoint(FULL)"
            )

        # CREAR ARCHIVO ZIP

        with zipfile.ZipFile(
            ruta,
            "w",
            zipfile.ZIP_DEFLATED
        ) as z:

            # INCLUIR BASE DE DATOS

            if DB_PATH.exists():

                z.write(
                    DB_PATH,
                    "database/investigacion.db"
                )

            # INCLUIR DOCUMENTOS SUBIDOS

            if UPLOAD_DIR.exists():

                for f in UPLOAD_DIR.rglob("*"):

                    if f.is_file():

                        z.write(
                            f,
                            str(
                                Path("static/uploads")
                                / f.relative_to(UPLOAD_DIR)
                            )
                        )

        # REGISTRAR ACCIÓN EN AUDITORÍA

        with conectar_db() as db:

            auditar(
                db,
                "Generó respaldo",
                "sistema",
                None,
                nombre
            )

        # DESCARGAR RESPALDO

        return send_from_directory(
            str(destino),
            nombre,
            as_attachment=True
        )

    # ========================================================
    # CONSULTAR ESTADO DE LA BASE DE DATOS
    # ========================================================

    with conectar_db() as db:

        integrity = db.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

    # ========================================================
    # INTERFAZ DE SEGURIDAD
    # ========================================================

    html = f"""
        <div class="card">

            <h2>
                Estado de base de datos: {integrity}
            </h2>

            <p>
                El respaldo incluye SQLite y los documentos
                almacenados en static/uploads.
            </p>

            <form method="post">

                <button type="submit">
                    Generar y descargar respaldo ZIP
                </button>

            </form>

        </div>

        <div class="card">

            <p>
                Guarda el ZIP fuera del equipo.
                La restauración debe realizarse con la
                aplicación detenida y verificando previamente
                el archivo.
            </p>

        </div>
    """

    return html_innovacion(
        "Seguridad y copias de respaldo",
        html
    )


# 25 Asistente inteligente orientativo (sin fuentes inventadas)
@app.route("/innovaciones/asistente-inteligente",methods=["GET","POST"])
@login_requerido
def asistente_inteligente():
    respuesta=''
    if request.method=='POST':
        tema=request.form.get('tema','').strip();problema=request.form.get('problema','').strip();objetivo=request.form.get('objetivo','').strip()
        if not tema: respuesta='Escribe un tema concreto para poder delimitarlo.'
        else:
            respuesta=f"Tema recibido: {tema}.\n\nPara delimitarlo, especifica población, lugar y periodo.\n\nPregunta orientativa: ¿Qué relación/efecto/características presenta {tema} en una población y contexto definidos?\n\nSiguiente paso: {('revisa si el problema '+problema+' puede observarse o medirse.' if problema else 'describe una situación observable que justifique el estudio.')}\n\nObjetivo: {('comprueba que '+objetivo+' comience con un verbo en infinitivo y sea verificable.' if objetivo else 'formula un objetivo general con un verbo en infinitivo.')}\n\nNo se han generado referencias bibliográficas. Busca y verifica las fuentes en la Biblioteca Virtual o en repositorios académicos."
    html='<div class="card"><p>Ayuda para ordenar ideas y planificar pasos. No sustituye al tutor y no inventa citas, datos ni bibliografía.</p><form method="post"><label>Tema</label><input name="tema" required><label>Problema que observas</label><textarea name="problema"></textarea><label>Objetivo que tienes pensado</label><textarea name="objetivo"></textarea><button>Obtener orientación</button></form></div>'
    if respuesta:html+='<div class="card"><h2>Orientación</h2><pre style="white-space:pre-wrap">'+__import__('html').escape(respuesta)+'</pre></div>'
    return html_innovacion("Asistente inteligente de investigación",html)


# 27 Mapa de conocimientos
@app.route("/innovaciones/investigacion/<int:investigacion_id>/mapa")
@login_requerido
def mapa_conocimientos(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id):return "Sin permiso",403
    with conectar_db() as db:items=db.execute("SELECT * FROM mapa_conocimientos WHERE investigacion_id=? ORDER BY id",(investigacion_id,)).fetchall()
    html='<div class="grid">'
    for item in items:html+=f'<div class="card"><h2>{item["elemento"]}</h2><p>{item["contenido"] or "Pendiente de desarrollar"}</p></div>'
    html+='</div><div class="card"><p>Relación recomendada: tema → problema → objetivos → metodología → resultados → conclusiones. Comprueba que cada apartado responda al anterior.</p><a class="btn" href="'+url_for('asistente_investigacion',investigacion_id=investigacion_id)+'">Editar mapa</a></div>'
    return html_innovacion("Mapa de conocimientos",html)


# 28 Feria digital de investigaciones
@app.route("/innovaciones/feria",methods=["GET","POST"])
@login_requerido
def feria_digital():
    u=usuario_actual()
    with conectar_db() as db:
        if request.method=='POST':
            if u['rol'] not in ('admin','tutor'):return "Sin permiso",403
            iid=request.form.get('investigacion_id',type=int); resumen=request.form.get('resumen','').strip();resultado=request.form.get('resultado','').strip();aut=1 if request.form.get('autorizada')=='1' else 0
            if not iid or not resumen:return "Faltan datos",400
            inv=db.execute("SELECT profesor_id,finalizada FROM investigaciones WHERE id=?",(iid,)).fetchone()
            if not inv or (u['rol']=='tutor' and inv['profesor_id']!=u['id']) or not inv['finalizada']:return "Solo se publican trabajos finalizados bajo tu responsabilidad.",403
            db.execute("INSERT INTO feria_digital(investigacion_id,resumen,resultado,autorizada,publicada_por) VALUES(?,?,?,?,?) ON CONFLICT(investigacion_id) DO UPDATE SET resumen=excluded.resumen,resultado=excluded.resultado,autorizada=excluded.autorizada,publicada_por=excluded.publicada_por,publicada_en=CURRENT_TIMESTAMP",(iid,resumen,resultado,aut,u['id']));auditar(db,"Actualizó ficha de feria","investigacion",iid)
        rows=db.execute("SELECT f.*,i.titulo,i.area_principal,i.subarea,g.nombre grupo FROM feria_digital f JOIN investigaciones i ON i.id=f.investigacion_id JOIN grupos g ON g.id=i.grupo_id WHERE f.autorizada=1 ORDER BY f.destacada DESC,f.publicada_en DESC").fetchall()
        if u['rol'] in ('admin','tutor'):
            pendientes=db.execute("SELECT i.id,i.titulo FROM investigaciones i WHERE i.finalizada=1 AND (i.profesor_id=? OR ?='admin')",(u['id'],u['rol'])).fetchall()
        else:pendientes=[]
    html=''.join(f'<div class="card"><h2>{r["titulo"]}</h2><p>{r["grupo"]} · {r["area_principal"]}/{r["subarea"]}</p><p>{r["resumen"]}</p><p><b>Resultado:</b> {r["resultado"] or "No especificado"}</p></div>' for r in rows) or '<div class="card">Todavía no hay investigaciones autorizadas para la feria.</div>'
    if pendientes:
        html+='<div class="card"><h2>Publicar investigación finalizada</h2><form method="post"><label>Proyecto</label><select name="investigacion_id">'+''.join(f'<option value="{p["id"]}">{p["titulo"]}</option>' for p in pendientes)+'</select><label>Resumen</label><textarea name="resumen" required></textarea><label>Resultados</label><textarea name="resultado"></textarea><label><input style="width:auto" type="checkbox" name="autorizada" value="1"> Tengo autorización institucional y de los autores para publicar</label><button>Guardar ficha</button></form></div>'
    return html_innovacion("Feria digital de investigaciones",html)


# 29 Evolución académica comparando rúbricas y notas reales
@app.route("/innovaciones/investigacion/<int:investigacion_id>/evolucion")
@login_requerido
def evolucion_academica(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id):return "Sin permiso",403
    with conectar_db() as db:
        rows=db.execute("SELECT nivel,version,estado,nota,enviado_en,revisado_en FROM historial_entregas WHERE investigacion_id=? ORDER BY nivel,version",(investigacion_id,)).fetchall()
        rub=db.execute("SELECT nivel,AVG(puntaje) promedio,COUNT(*) criterios FROM rubricas WHERE investigacion_id=? GROUP BY nivel ORDER BY nivel",(investigacion_id,)).fetchall()
    html='<div class="card"><h2>Evolución por entrega</h2><table><tr><th>Nivel</th><th>Versión</th><th>Estado</th><th>Nota registrada</th><th>Enviado</th><th>Revisado</th></tr>'
    for r in rows:html+=f'<tr><td>{r["nivel"]}</td><td>{r["version"]}</td><td>{r["estado"]}</td><td>{r["nota"] if r["nota"] is not None else "—"}</td><td>{r["enviado_en"]}</td><td>{r["revisado_en"] or "—"}</td></tr>'
    html+='</table></div><div class="card"><h2>Promedio de rúbricas</h2>'+''.join(f'<p>Nivel {r["nivel"]}: {round(r["promedio"],1)}/100 ({r["criterios"]} evaluaciones)</p>' for r in rub)+'</div><div class="card"><p>La comparación solo muestra datos realmente registrados; si no hay nota, no se estima ni se inventa.</p></div>'
    return html_innovacion("Indicador de evolución académica",html)


# 30 Trazabilidad completa: registro de eventos de varias áreas
@app.route("/innovaciones/investigacion/<int:investigacion_id>/trazabilidad")
@login_requerido
def trazabilidad_investigacion(investigacion_id):
    u=usuario_actual()
    if not exigir_acceso_investigacion(u,investigacion_id):return "Sin permiso",403
    with conectar_db() as db:
        rows=db.execute("SELECT a.*,u.nombre,u.apellido FROM auditoria_tesislab a LEFT JOIN usuarios u ON u.id=a.usuario_id WHERE a.entidad_id=? ORDER BY a.creado_en DESC LIMIT 200",(investigacion_id,)).fetchall()
        hist=db.execute("SELECT nivel,version,estado,enviado_en,revisado_en FROM historial_entregas WHERE investigacion_id=? ORDER BY enviado_en DESC",(investigacion_id,)).fetchall()
        prog=db.execute("SELECT nivel,evento,fecha FROM historial_progreso WHERE investigacion_id=? ORDER BY fecha DESC",(investigacion_id,)).fetchall()
    html='<div class="card"><h2>Entregas y revisiones</h2>'+''.join(f'<p>Nivel {h["nivel"]} · v{h["version"]} · {h["estado"]} · {h["enviado_en"]} · Revisión: {h["revisado_en"] or "pendiente"}</p>' for h in hist)+'</div><div class="card"><h2>Progreso</h2>'+''.join(f'<p>{p["fecha"]} · Nivel {p["nivel"]} · {p["evento"]}</p>' for p in prog)+'</div><div class="card"><h2>Actividad registrada</h2>'+''.join(f'<p>{a["creado_en"]} · {a["nombre"] or "Usuario"} {a["apellido"] or ""} · {a["accion"]} · {a["detalle"] or ""}</p>' for a in rows)+'</div>'
    return html_innovacion("Trazabilidad de la investigación",html)


# Instrumentación de cambios críticos futuros y menú de acceso
@app.context_processor
def inyectar_menu_innovaciones():
    if not session.get('usuario_id'): return {}
    return {'url_innovaciones': url_for('innovaciones_inicio'), 'url_comunicados': url_for('ver_comunicados')}

@app.route("/diagnostico-rutas")
@login_requerido
def diagnostico_rutas():

    if usuario_actual()["rol"] != "admin":
        return "No autorizado", 403

    reglas = []

    for regla in app.url_map.iter_rules():

        if "biblioteca" in regla.rule or "historial" in regla.rule:
            reglas.append({
                "ruta": regla.rule,
                "endpoint": regla.endpoint,
                "metodos": sorted(regla.methods)
            })

    return {
        "rutas": reglas
    }


with conectar_db() as db:
    cursos = db.execute("""
        SELECT DISTINCT curso
        FROM usuarios
        WHERE rol = 'estudiante'
        ORDER BY curso
    """).fetchall()

    print("\n========== CURSOS REGISTRADOS ==========")

    for curso in cursos:
        print(curso["curso"])

    print("========================================\n")


# ============================================================
# INFORMES AUTOMÁTICOS - ADMINISTRADOR
# ============================================================

@app.route("/admin/informes")
@login_requerido
def admin_informes():

    usuario = usuario_actual()

    if usuario["rol"] != "admin":
        flash("No tienes permiso para consultar los informes.", "error")
        return redirect(url_for("panel"))

    cursos = ["5to A", "5to B", "5to C"]

    informe_cursos = []

    with conectar_db() as db:

        for curso in cursos:

            investigaciones = db.execute("""
                SELECT
                    i.id,
                    i.nota_final,
                    i.finalizada,
                    i.estado,
                    i.nivel_actual,

                    COUNT(
                        CASE
                            WHEN LOWER(TRIM(ni.estado)) = 'aprobado'
                            THEN 1
                        END
                    ) AS niveles_aprobados

                FROM investigaciones i

                INNER JOIN grupos g
                    ON g.id = i.grupo_id

                INNER JOIN usuarios u
                    ON u.id = g.lider_id

                LEFT JOIN niveles_investigacion ni
                    ON ni.investigacion_id = i.id

                WHERE u.curso = ?

                GROUP BY i.id

            """, (curso,)).fetchall()

            total = len(investigaciones)

            if total:

                avances = [
                    round(fila["niveles_aprobados"] * 100 / 6)
                    for fila in investigaciones
                ]

                notas = [
                    fila["nota_final"]
                    for fila in investigaciones
                    if fila["nota_final"] is not None
                ]

                avance_promedio = round(sum(avances) / total)

                nota_promedio = (
                    round(sum(notas) / len(notas), 1)
                    if notas else None
                )

                en_riesgo = sum(
                    1 for fila in investigaciones
                    if not fila["finalizada"]
                    and fila["niveles_aprobados"] < 3
                )

                finalizadas = sum(
                    1 for fila in investigaciones
                    if fila["finalizada"]
                )

            else:
                avance_promedio = 0
                nota_promedio = None
                en_riesgo = 0
                finalizadas = 0

            informe_cursos.append({
                "curso": curso,
                "investigaciones": total,
                "avance_promedio": avance_promedio,
                "nota_promedio": nota_promedio,
                "en_riesgo": en_riesgo,
                "finalizadas": finalizadas
            })

    return render_template(
        "informes_admin.html",
        usuario=usuario,
        informe_cursos=informe_cursos
    )

@app.route(
    "/innovaciones/admin/auditoria/probar",
    methods=["POST"]
)
@roles_requeridos("admin")
def probar_integridad_auditoria():

    prueba = {
        "id": 999999,
        "usuario_id": session.get("usuario_id"),
        "accion": "PRUEBA DE SEGURIDAD",
        "entidad": "auditoria",
        "entidad_id": None,
        "detalle": "Registro original de prueba",
        "ip": "LOCAL",
        "creado_en": "2026-11-05 12:00:00",
        "hash_anterior": "GENESIS",
        "hash_actual": None
    }

    hash_original = calcular_hash_auditoria(prueba)

    # Simular una modificación.
    prueba["detalle"] = "Registro modificado intencionalmente"

    hash_modificado = calcular_hash_auditoria(prueba)

    detectada = hash_original != hash_modificado

    if detectada:

        flash(
            "Prueba superada: SHA-256 detectó la modificación.",
            "success"
        )

    else:

        flash(
            "Error: no se detectó la modificación.",
            "error"
        )

    return redirect(
        url_for("registro_auditoria")
    )
# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    inicializar_db()
    asegurar_innovaciones()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
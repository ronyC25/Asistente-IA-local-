"""Logica de confirmacion de acciones pendientes (sin dependencias de red)."""
from __future__ import annotations

import calendar as _calendar
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

_YES = {
    "si",
    "s",
    "claro",
    "confirmo",
    "confirmar",
    "confirmado",
    "confirmalo",
    "ok",
    "okay",
    "dale",
    "adelante",
    "hazlo",
    "hacelo",
    "correcto",
    "afirmativo",
    "yes",
    "y",
    "vale",
    "perfecto",
    "de acuerdo",
    "por supuesto",
    "obvio",
    "efectivamente",
}

_NO = {
    "no",
    "n",
    "cancelar",
    "cancela",
    "cancela lo",
    "cancelo",
    "negativo",
    "no gracias",
    "espera",
    "para",
    "detente",
    "mejor no",
    "nunca",
    "olvidalo",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# Verbos que indican que el usuario pide una ACCION (no solo una consulta).
_ACTION_VERBS = {
    "manda",
    "mandame",
    "envia",
    "enviame",
    "crea",
    "creame",
    "agenda",
    "agendame",
    "programa",
    "programame",
    "recuerdame",
    "recordarme",
    "elimina",
    "borra",
    "edita",
    "cambia",
    "cancela",
    "completa",
    "marca",
    "responde",
    "escribe",
    "anade",
    "agrega",
    "exporta",
    "avisame",
    "avisa",
}


def looks_like_action(text: str) -> bool:
    """Heuristica: True si el mensaje parece pedir una accion de escritura."""
    t = _norm(text)
    if not t:
        return False
    palabras = set(t.split())
    return bool(palabras & _ACTION_VERBS)


# Verbos/sustantivos que indican una CONSULTA (lectura de datos).
_QUERY_WORDS = {
    "revisa",
    "revisar",
    "revisame",
    "revisen",
    "busca",
    "buscar",
    "buscame",
    "encuentra",
    "encuentrame",
    "localiza",
    "lista",
    "listar",
    "listame",
    "muestra",
    "muestrame",
    "mostrar",
    "dime",
    "consulta",
    "consultar",
    "cuantas",
    "cuantos",
    "cuanto",
    "cuanta",
    "queda",
    "quedan",
    "falta",
    "faltan",
    "cuales",
    "cual",
    "tengo",
    "hay",
    "ver",
    "veamos",
    "pendientes",
    "agenda",
    "calendario",
    "eventos",
    "recordatorios",
    "tareas",
    "correos",
    "correo",
    "emails",
    "nota",
    "notas",
    "apunte",
    "apuntes",
    "notificacion",
    "notificaciones",
    "aviso",
    "avisos",
    "alarma",
    "alarmas",
    "checklist",
    "checklists",
    "hoy",
    "manana",
}


def looks_like_query(text: str) -> bool:
    """Heuristica: True si el mensaje parece pedir una consulta (lectura)."""
    t = _norm(text)
    if not t:
        return False
    palabras = set(t.split())
    return bool(palabras & _QUERY_WORDS)


# Dominio de datos -> palabras clave (sustantivos, sin ambiguedad de verbos).
_DOMINIO_KEYWORDS = (
    (
        "recordatorios",
        (
            "notificacion",
            "notificaciones",
            "recordatorio",
            "recordatorios",
            "aviso",
            "avisos",
            "alarma",
            "alarmas",
        ),
    ),
    ("tareas", ("tarea", "tareas")),
    ("notas", ("nota", "notas", "apunte", "apuntes")),
    (
        "listas",
        ("checklist", "checklists", "lista de la compra", "lista de compras"),
    ),
    (
        "temporizadores",
        (
            "pomodoro",
            "pomodoros",
            "temporizador",
            "temporizadores",
            "cronometro",
            "cronometros",
        ),
    ),
    (
        "eventos",
        ("evento", "eventos", "calendario", "agenda", "cita", "citas", "reunion", "reuniones"),
    ),
    ("email", ("correo", "correos", "email", "emails")),
)


def dominio_lectura(text: str) -> str | None:
    """Detecta el dominio de datos de una consulta (p. ej. 'notificaciones').

    Devuelve una clave de dominio ('tareas', 'recordatorios', 'notas', 'listas',
    'eventos', 'email', 'busqueda') o None. 'notificaciones' cuenta como
    recordatorios. 'busqueda' = pedir buscar algo sin indicar dominio.
    """
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    for dominio, claves in _DOMINIO_KEYWORDS:
        for k in claves:
            if (" " in k and k in t) or (" " not in k and k in palabras):
                return dominio
    if es_busqueda(text):
        return "busqueda"
    return None


_BUSQUEDA_WORDS = {
    "busca",
    "buscar",
    "buscame",
    "buscarlo",
    "encuentra",
    "encuentrame",
    "localiza",
    "localizame",
}
_BUSQUEDA_STOP = {
    "busca",
    "buscar",
    "buscame",
    "buscarlo",
    "encuentra",
    "encuentrame",
    "localiza",
    "localizame",
    "donde",
    "esta",
    "estan",
    "queda",
    "quedan",
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "de",
    "del",
    "en",
    "sobre",
    "algo",
    "que",
    "por",
    "favor",
    "mi",
    "mis",
    "todo",
    "todos",
    "toda",
    "todas",
    "hay",
    "existe",
    "existen",
    "me",
    "puedes",
    "puede",
    "a",
    "al",
}


def es_busqueda(text: str) -> bool:
    """True si el usuario pide buscar algo (sin dominio concreto)."""
    t = _norm(text)
    if not t:
        return False
    if set(t.split()) & _BUSQUEDA_WORDS:
        return True
    return any(
        frase in t
        for frase in ("donde esta", "donde estan", "donde queda", "donde quedan")
    )


def buscar_termino_de_texto(text: str) -> str | None:
    """Extrae el termino a buscar quitando palabras-gatillo ('busca', 'donde esta'...).

    Devuelve None si tras limpiar no queda nada util.
    """
    t = _norm(text)
    if not t:
        return None
    palabras = [w for w in t.split() if w not in _BUSQUEDA_STOP]
    termino = " ".join(palabras).strip()
    return termino or None


def etiqueta_de_texto(text: str) -> str | None:
    """Extrae una etiqueta de frases como 'etiquetadas como compras' o 'etiqueta X'."""
    t = _norm_keep(text)
    if not t:
        return None
    m = re.search(
        r"(?:etiquetad[oa]s?|etiqueta|categoria|categorias?|tag)\s+"
        r"(?:como\s+)?(?:de\s+|la\s+|el\s+|las\s+|los\s+|con\s+)?([a-z0-9\- ]{2,40})",
        t,
    )
    if not m:
        return None
    cand = re.split(r"\b(?:de|del|en|para|que|con|y|o|por)\b", m.group(1))[0].strip()
    return cand or None


# --- temporizadores / pomodoro ---
_NUM_WORDS = (
    r"(?:\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince)"
)


def minutos_de_texto(text: str) -> int | None:
    """Extrae una duracion en minutos ('25 minutos', '1 hora', 'media hora', '1h30')."""
    t = _norm_keep(text)
    if not t:
        return None
    if "hora y media" in t or "hora y medio" in t:
        return 90
    if "media hora" in t:
        return 30
    m = re.search(rf"({_NUM_WORDS})\s*horas?\s*y\s*media", t)
    if m:
        n = _num(m.group(1))
        if n:
            return n * 60 + 30
    m = re.search(rf"({_NUM_WORDS})\s*horas?", t)
    if m:
        n = _num(m.group(1))
        if n:
            return n * 60
    m = re.search(r"(\d+)\s*h(?:\s*(\d{1,2}))?", t)
    if m:
        h = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        if h or mm:
            return h * 60 + mm
    m = re.search(rf"({_NUM_WORDS})\s*min", t)
    if m:
        return _num(m.group(1))
    return None


_INICIAR_WORDS = {
    "inicia",
    "iniciar",
    "iniciame",
    "empieza",
    "empezar",
    "arranca",
    "arrancar",
    "lanza",
    "lanzar",
    "comienza",
    "comenzar",
    "activa",
    "activar",
    "pon",
    "poner",
    "ponme",
}
_CANCELAR_WORDS = {
    "cancela",
    "cancelar",
    "cancelame",
    "deten",
    "detener",
    "parar",
    "termina",
    "terminar",
    "elimina",
    "borra",
}
_CANCELAR_PARA_RE = re.compile(
    r"^para\s+(?:el\s+|la\s+|los\s+|las\s+)?"
    r"(?:pomodoro|pomodoros|temporizador|temporizadores|cronometro|timer)\b"
)
_PAUSAR_WORDS = {"pausa", "pausar", "pausalo", "pausame"}
_REANUDAR_WORDS = {"reanuda", "reanudar", "reanudalo", "continua", "continuar", "resume"}
_TIMER_WORDS = {
    "pomodoro",
    "pomodoros",
    "temporizador",
    "temporizadores",
    "cronometro",
    "cronometros",
    "timer",
}


def _etiqueta_timer(t: str) -> str | None:
    """Extrae la etiqueta de un temporizador ('para el horno', 'del horno')."""
    for pat in (
        r"\bpara\s+(?:el\s+|la\s+|los\s+|las\s+)?([a-z0-9\- ]{2,30})",
        r"\b(?:del|de)\s+(?:el\s+|la\s+)?([a-z0-9\- ]{2,30})",
        r"\b(?:con\s+etiqueta|etiqueta)\s+(?:de\s+|el\s+|la\s+)?([a-z0-9\- ]{2,30})",
    ):
        m = re.search(pat, t)
        if not m:
            continue
        cand = re.split(
            r"\b(?:de|del|en|que|con|y|o|por|las?|los?|el)\b", m.group(1)
        )[0].strip()
        cand = re.sub(r"\b\d+\b.*$", "", cand).strip()
        if cand and cand not in _TIMER_WORDS:
            return cand
    return None


def intencion_temporizador(text: str) -> dict | None:
    """Detecta iniciar/cancelar un temporizador o pomodoro.

    Devuelve ``{"accion", "tipo", "minutos", "etiqueta", "id"}`` o None. Sirve
    para gestionar la accion de forma determinista (sin depender del modelo).
    """
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    if not (palabras & _TIMER_WORDS):
        return None
    tipo = (
        "pomodoro"
        if ("pomodoro" in palabras or "pomodoros" in palabras)
        else "temporizador"
    )
    if palabras & _CANCELAR_WORDS or _CANCELAR_PARA_RE.match(t):
        etq = _etiqueta_timer(t)
        idv = None
        if not etq:
            idm = re.search(r"\b(\d+)\b", t)
            idv = int(idm.group(1)) if idm else None
        return {"accion": "cancelar", "tipo": tipo, "etiqueta": etq, "id": idv}
    if palabras & _PAUSAR_WORDS:
        return {
            "accion": "pausar",
            "tipo": tipo,
            "etiqueta": _etiqueta_timer(t),
            "id": None,
        }
    if palabras & _REANUDAR_WORDS:
        return {
            "accion": "reanudar",
            "tipo": tipo,
            "etiqueta": _etiqueta_timer(t),
            "id": None,
        }
    minutos = minutos_de_texto(text)
    if (palabras & _INICIAR_WORDS) or minutos:
        return {
            "accion": "iniciar",
            "tipo": tipo,
            "minutos": minutos,
            "etiqueta": _etiqueta_timer(t),
            "id": None,
        }
    return None


_REF_PASADO_RE = re.compile(
    r"(que ya paso|ya paso|que ya ocurrio|ya ocurrio|que ya termino|ya termino)"
)
_REF_PRONOMBRE = {
    "lo",
    "la",
    "los",
    "las",
    "ese",
    "esa",
    "eso",
    "esto",
    "esta",
    "aquel",
    "aquella",
}


def referencia_evento(text: str) -> str | None:
    """Clasifica una referencia a un evento.

    Devuelve 'hoy_pasado', 'ultimo_pasado', 'proximo' o 'antiguo' (o None).
    """
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    if _REF_PASADO_RE.search(t):
        return "hoy_pasado" if "hoy" in palabras else "ultimo_pasado"
    if "de hoy" in t or "hoy" in palabras:
        if not (palabras & {"proximo", "proxima", "siguiente", "futuro"}):
            return "hoy_pasado"
    if palabras & {"ultimo", "ultima", "pasado", "pasada", "anterior"}:
        return "ultimo_pasado"
    if palabras & {"proximo", "proxima", "siguiente"}:
        return "proximo"
    if palabras & {"antiguo", "antigua", "primero", "primera", "viejo", "vieja"}:
        return "antiguo"
    return None


_REF_OBJETO_RE = re.compile(r"\b(?:cancel|borr|elimin|anul|quit|remov)\w*(?:lo|la|los|las)\b")
_CANCEL_VERBS = {
    "cancela",
    "cancelar",
    "cancelalo",
    "cancelala",
    "elimina",
    "eliminar",
    "eliminalo",
    "borra",
    "borrar",
    "borralo",
    "anula",
    "anular",
    "quita",
    "quitar",
    "remueve",
    "remover",
}


def es_cancelacion(text: str) -> bool:
    """True si el usuario pide cancelar/eliminar algo."""
    return bool(set(_norm(text).split()) & _CANCEL_VERBS)


_PASADO_WORDS = {"hubo", "hubieron", "tuve", "pasaron", "ocurrieron", "sucedieron"}


def quiere_eventos_pasados(text: str) -> bool:
    """True si el usuario pregunta por eventos YA ocurridos ('que hubo hoy')."""
    t = _norm(text)
    if not t:
        return False
    if any(
        p in t
        for p in ("ya paso", "ya pasaron", "ya ocurrio", "ya ocurrieron", "que paso")
    ):
        return True
    return bool(set(t.split()) & _PASADO_WORDS)


def es_referencia_objeto(text: str) -> bool:
    """True si usa un pronombre/anafora ('lo', 'ese', 'eso', 'cancelalo'...)."""
    t = _norm(text)
    if set(t.split()) & _REF_PRONOMBRE:
        return True
    return bool(_REF_OBJETO_RE.search(t))


def orden_de_texto(text: str) -> str | None:
    """Detecta 'lo mas antiguo' o 'lo mas reciente' (None si no aplica)."""
    t = _norm(text)
    if not t:
        return None
    palabras = set(t.split())
    if palabras & {
        "antiguo",
        "antigua",
        "antiguos",
        "antiguas",
        "viejo",
        "vieja",
        "viejos",
        "viejas",
    }:
        return "antiguas"
    if palabras & {
        "reciente",
        "recientes",
        "ultimo",
        "ultima",
        "ultimos",
        "ultimas",
    }:
        return "recientes"
    return None


def quiere_proximo(text: str) -> bool:
    """True si piden el proximo/siguiente (p. ej. 'el evento mas proximo')."""
    palabras = set(_norm(text).split())
    return bool(
        palabras
        & {"proximo", "proxima", "proximos", "proximas", "siguiente", "siguientes"}
    )


def pregunta_cuanto_falta(text: str) -> bool:
    """True si preguntan cuanto falta/queda para algo."""
    t = _norm(text)
    return (
        "cuanto falta" in t
        or "cuanto queda" in t
        or "cuanto tiempo" in t
        or "falta para" in t
    )


# --- fechas explicitas / rangos relativos ampliados ---
def _norm_keep(text: str) -> str:
    """Normaliza (minusculas, sin acentos) pero CONSERVANDO separadores (/,-,:)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_NUMS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "quince": 15,
}


def _num(s: str) -> int | None:
    s = s.lower()
    return int(s) if s.isdigit() else _NUMS.get(s)


def fecha_de_texto(text: str, hoy: date | None = None) -> date | None:
    """Extrae una fecha explicita ('28 de octubre', '28/10/2026', '2026-10-28').

    Si no se indica el ano y la fecha ya paso este ano, se usa el ano siguiente.
    """
    t = _norm_keep(text)
    if not t:
        return None
    hoy = hoy or date.today()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else hoy.year
        if y < 100:
            y += 2000
        try:
            f = date(y, mo, d)
        except ValueError:
            return None
        if not m.group(3) and f < hoy:
            f = date(y + 1, mo, d)
        return f
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?", t)
    if m:
        mo = _MESES.get(m.group(2))
        if not mo:
            return None
        y = int(m.group(3)) if m.group(3) else hoy.year
        try:
            f = date(y, mo, int(m.group(1)))
        except ValueError:
            return None
        if not m.group(3) and f < hoy:
            f = date(y + 1, mo, int(m.group(1)))
        return f
    return None


def _semana_de_mes(year: int, mes: int, cual: str) -> tuple[date, date] | None:
    """Rango de una semana (bloques de 7 dias desde el dia 1) de un mes."""
    ultimo = _calendar.monthrange(year, mes)[1]
    if cual == "primera":
        return (date(year, mes, 1), date(year, mes, 7))
    if cual == "segunda":
        return (date(year, mes, 8), date(year, mes, 14))
    if cual == "tercera":
        return (date(year, mes, 15), date(year, mes, 21))
    if cual == "cuarta":
        return (date(year, mes, 22), date(year, mes, 28))
    if cual == "quinta":
        if ultimo < 29:
            return None
        return (date(year, mes, 29), date(year, mes, ultimo))
    if cual == "ultima":
        return (date(year, mes, ultimo - 6), date(year, mes, ultimo))
    if cual in ("penultima", "anteultima"):
        ini = ultimo - 13
        if ini < 1:
            return None
        return (date(year, mes, ini), date(year, mes, ultimo - 7))
    return None


def rango_de_texto(text: str, hoy: date | None = None) -> tuple[date, date] | None:
    """Rangos relativos ampliados: 'de aqui a N semanas/meses', 'en N dias',
    'la ultima semana de octubre', 'la primera semana del mes'..."""
    t = _norm_keep(text)
    if not t:
        return None
    hoy = hoy or date.today()

    # Semanas de un mes (o del mes actual si no se indica).
    m = re.search(
        r"(primera|segunda|tercera|cuarta|quinta|penultima|anteultima|ultima)\s+semana"
        r"(?:\s+de\s+([a-z]+)(?:\s+de\s+(\d{4}))?|\s+del\s+mes(?:\s+de\s+(\d{4}))?)?",
        t,
    )
    if m:
        cual = m.group(1)
        if m.group(2):
            mes = _MESES.get(m.group(2))
            if not mes:
                return None
            year = int(m.group(3)) if m.group(3) else hoy.year
        else:
            mes = hoy.month
            year = int(m.group(4)) if m.group(4) else hoy.year
        r = _semana_de_mes(year, mes, cual)
        if r:
            return r

    m = re.search(
        r"(de aqui a|en|proximas?|proximos?|siguientes?)\s+"
        r"(\d{1,3}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince)\s+"
        r"(dias?|semanas?|meses?)",
        t,
    )
    if not m:
        return None
    n = _num(m.group(2))
    if not n:
        return None
    prefijo, unidad = m.group(1), m.group(3)
    if unidad.startswith("dia"):
        fin = hoy + timedelta(days=n)
    elif unidad.startswith("semana"):
        fin = hoy + timedelta(weeks=n)
    else:  # mes
        fin = hoy + relativedelta(months=n)
    if prefijo == "en":
        return (fin, fin)
    return (hoy, fin)


_CAPACIDADES_FRASES = (
    "que puedes hacer",
    "que sabes hacer",
    "que eres capaz",
    "de que eres capaz",
    "que funciones",
    "tus funciones",
    "que capacidades",
    "tus capacidades",
    "para que sirves",
    "que herramientas",
    "tus herramientas",
    "que comandos",
    "lista de funciones",
    "muestrame tus funciones",
    "en que puedes ayudar",
    "en que me puedes ayudar",
    "como puedes ayudar",
)
_CAPACIDADES_EXACTAS = {
    "/ayuda",
    "/help",
    "/funciones",
    "/capacidades",
    "ayuda",
    "help",
    "funciones",
    "capacidades",
}


def pregunta_capacidades(text: str) -> bool:
    """True si el usuario pregunta que puede hacer el asistente (o pide ayuda)."""
    raw = (text or "").strip().lower()
    if raw in _CAPACIDADES_EXACTAS:
        return True
    t = _norm(text)
    if not t:
        return False
    return any(frase in t for frase in _CAPACIDADES_FRASES)


_HISTORIAL_WORDS = {
    "lista",
    "listado",
    "listame",
    "todos",
    "todas",
    "historial",
    "completos",
    "completas",
    "cuales",
}
_PENDIENTE_WORDS = {
    "pendiente",
    "pendientes",
    "proximo",
    "proximos",
    "vencen",
    "vencido",
    "vencidos",
    "futuro",
    "futuros",
    "activo",
    "activos",
}


def quiere_historial_recordatorios(text: str) -> bool:
    """True si el usuario pide el historial de recordatorios (no solo pendientes)."""
    t = _norm(text)
    if not t:
        return False
    if "cancelad" in t:  # pide cancelados explicitamente
        return False
    palabras = set(t.split())
    if palabras & _PENDIENTE_WORDS:
        return False
    return bool(palabras & _HISTORIAL_WORDS)


_WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def periodo_de_texto(text: str) -> tuple[str, int | None] | None:
    """Detecta una expresion de rango relativo y devuelve (periodo, dias) o None.

    Sirve para resolver fechas de forma determinista (sin que el modelo calcule).
    """
    t = _norm(text)
    if not t:
        return None
    if "pasado manana" in t:
        return ("pasado_manana", None)
    if "fin de semana" in t or "finde" in t:
        return ("fin_de_semana", None)
    if any(
        frase in t
        for frase in (
            "semana que viene",
            "proxima semana",
            "semana siguiente",
            "la otra semana",
        )
    ):
        return ("semana_que_viene", None)
    if "esta semana" in t:
        return ("esta_semana", None)
    if any(
        frase in t
        for frase in ("semana pasada", "semana anterior", "la anterior semana")
    ):
        return ("semana_pasada", None)
    if "este mes" in t or "mes en curso" in t:
        return ("este_mes", None)
    m = re.search(r"(?:proximos|proximas|siguientes)\s+(\d+)\s+dias?", t)
    if m:
        return ("proximos_dias", int(m.group(1)))
    if "hoy" in t:
        return ("hoy", None)
    if "manana" in t:
        return ("manana", None)
    for wd in _WEEKDAYS:
        if re.search(rf"\b{wd}\b", t):
            return (wd, None)
    return None


def classify_confirmation(text: str) -> bool | None:
    """Devuelve True (confirmar), False (cancelar) o None (ambiguo)."""
    t = _norm(text)
    if not t:
        return None

    def matches(word_set: set[str]) -> bool:
        if t in word_set:
            return True
        first = t.split()[0]
        return first in word_set

    if matches(_NO):
        return False
    if matches(_YES):
        return True
    return None


def build_proposal(parsed: list[tuple[str, dict]], registry: Any) -> str:
    lines: list[str] = []
    for name, args in parsed:
        tool = registry.get(name)
        if tool is not None and tool.describe is not None:
            lines.append("• " + tool.describe(args or {}))
        else:
            params = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
            lines.append(f"• {name}({params})")
    body = "\n".join(lines)
    return (
        "Voy a realizar la siguiente accion:\n"
        f"{body}\n\n"
        "¿Confirmas? (si/no)"
    )

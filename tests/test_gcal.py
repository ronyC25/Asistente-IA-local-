from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src import config
from src.tools import calendar, gcal


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database", str(tmp_path / "test.db"))
    calendar._conn().close()
    (tmp_path / "cred.json").write_text("{}", encoding="utf-8")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        {
            "enabled": True,
            "calendar_id": "primary",
            "credentials_file": str(tmp_path / "cred.json"),
            "token_file": str(tmp_path / "token.json"),
            "timezone": "Europe/Madrid",
            "conflict_policy": "last_write_wins",
        },
    )
    yield tmp_path


def _futuro(dias: int = 1) -> str:
    return (datetime.now() + timedelta(days=dias)).isoformat(timespec="minutes")


class _FakeExec:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _FakeEvents:
    def __init__(self):
        self.inserted: list[dict] = []
        self.patched: list[tuple] = []
        self.deleted: list[str] = []
        self.listed: list[dict] = []
        self.list_response: dict = {"items": [], "nextSyncToken": "tok"}

    def insert(self, calendarId, body):
        self.inserted.append(body)
        return _FakeExec(
            {"id": "g-new", "updated": "2026-01-01T00:00:00Z", "etag": "e1"}
        )

    def patch(self, calendarId, eventId, body):
        self.patched.append((eventId, body))
        return _FakeExec(
            {"id": eventId, "updated": "2026-02-02T00:00:00Z", "etag": "e2"}
        )

    def delete(self, calendarId, eventId):
        self.deleted.append(eventId)
        return _FakeExec({})

    def list(self, **kwargs):
        self.listed.append(kwargs)
        return _FakeExec(self.list_response)


class _FakeService:
    def __init__(self):
        self._events = _FakeEvents()

    def events(self):
        return self._events


def _fake(monkeypatch) -> _FakeService:
    fake = _FakeService()
    monkeypatch.setattr(gcal, "_service", lambda: fake)
    return fake


# --- mapeo ---
def test_evento_a_google():
    ev = {
        "titulo": "Reunion",
        "inicio": "2026-03-01T10:00:00",
        "fin": "2026-03-01T11:00:00",
        "todo_el_dia": False,
        "lugar": "Oficina",
        "notas": "nota",
    }
    body = gcal._evento_a_google(ev)
    assert body["summary"] == "Reunion"
    assert body["start"]["dateTime"].startswith("2026-03-01T10:00:00")
    assert body["start"]["timeZone"] == "Europe/Madrid"
    assert body["location"] == "Oficina"
    assert body["description"] == "nota"


def test_evento_a_google_todo_el_dia():
    ev = {
        "titulo": "Festivo",
        "inicio": "2026-03-01T00:00:00",
        "fin": None,
        "todo_el_dia": True,
        "lugar": None,
        "notas": None,
    }
    body = gcal._evento_a_google(ev)
    assert body["start"] == {"date": "2026-03-01"}
    assert body["end"] == {"date": "2026-03-02"}
    assert "dateTime" not in body["start"]


def test_google_a_local_datetime():
    g = {
        "summary": "Cita",
        "start": {"dateTime": "2026-03-01T10:00:00+01:00"},
        "end": {"dateTime": "2026-03-01T11:00:00+01:00"},
    }
    d = gcal._google_a_local(g)
    assert d["titulo"] == "Cita"
    assert d["todo_el_dia"] is False
    assert d["inicio"].startswith("2026-03-01T")


def test_google_a_local_todo_el_dia():
    g = {
        "summary": "Festivo",
        "start": {"date": "2026-03-01"},
        "end": {"date": "2026-03-02"},
    }
    d = gcal._google_a_local(g)
    assert d["todo_el_dia"] is True
    assert d["inicio"].startswith("2026-03-01")


def test_parse_ts():
    assert gcal._parse_ts("2026-01-01T00:00:00Z").tzinfo is not None
    assert gcal._parse_ts("2026-01-01 00:00:00").tzinfo is not None
    assert gcal._parse_ts(None) is None
    assert gcal._parse_ts("basura") is None


def test_zona_horaria_config():
    assert gcal.zona_horaria() == "Europe/Madrid"


def test_disponible(monkeypatch):
    assert gcal.disponible() is True
    monkeypatch.setattr(
        config.settings,
        "google_calendar",
        dict(config.settings.google_calendar, enabled=False),
    )
    assert gcal.disponible() is False


# --- push ---
def test_push_inserta_y_marca(monkeypatch):
    fake = _fake(monkeypatch)
    ev = calendar.crear_evento("Reunion", _futuro(1))
    assert len(fake._events.inserted) == 1
    assert ev["gcal_id"] == "g-new"
    assert ev["pending_push"] is False


def test_push_edita_existente(monkeypatch):
    fake = _fake(monkeypatch)
    ev = calendar.crear_evento("Original", _futuro(1))
    calendar.guardar_gcal(ev["id"], "g-1", "u0", "e0")
    editado = calendar.editar_evento(ev["id"], titulo="Editado")
    assert fake._events.patched
    assert fake._events.patched[-1][0] == "g-1"
    assert editado["titulo"] == "Editado"
    assert editado["pending_push"] is False


def test_push_cancelado_borra(monkeypatch):
    fake = _fake(monkeypatch)
    ev = calendar.crear_evento("X", _futuro(1))
    calendar.guardar_gcal(ev["id"], "g-1", "u", "e")
    c = calendar.cancelar_evento(ev["id"])
    assert "g-1" in fake._events.deleted
    assert c["gcal_id"] is None
    assert c["estado"] == "cancelado"


# --- pull ---
def test_pull_crea_actualiza_y_cancela(monkeypatch):
    fake = _fake(monkeypatch)
    viejo = calendar.crear_evento("Viejo", _futuro(1))
    calendar.guardar_gcal(viejo["id"], "g-old", "2026-01-01T00:00:00Z", "e0")
    calendar.marcar_sincronizado(viejo["id"])
    borrar = calendar.crear_evento("Para cancelar", _futuro(2))
    calendar.guardar_gcal(borrar["id"], "g-del", "2026-01-01T00:00:00Z", "e0")
    calendar.marcar_sincronizado(borrar["id"])

    fake._events.list_response = {
        "items": [
            {
                "id": "g-new",
                "summary": "Nuevo",
                "updated": "2026-01-01T00:00:00Z",
                "start": {"date": "2026-05-01"},
                "end": {"date": "2026-05-02"},
            },
            {
                "id": "g-old",
                "summary": "Viejo editado",
                "updated": "2026-09-01T00:00:00Z",
                "start": {"dateTime": "2026-06-01T10:00:00+02:00"},
                "end": {"dateTime": "2026-06-01T11:00:00+02:00"},
            },
            {"id": "g-del", "status": "cancelled"},
        ],
        "nextSyncToken": "tok2",
    }
    r = gcal.pull_incremental()
    assert r["creados"] == 1
    assert r["actualizados"] == 1
    assert r["cancelados"] == 1
    assert calendar.obtener_por_gcal("g-new")["titulo"] == "Nuevo"
    assert calendar.obtener_por_gcal("g-old")["titulo"] == "Viejo editado"
    assert calendar.obtener_por_gcal("g-del")["estado"] == "cancelado"
    assert calendar.get_sync_token("primary") == "tok2"


def test_conflicto_gana_local_mas_reciente(monkeypatch):
    fake = _fake(monkeypatch)
    ev = calendar.crear_evento("Original", _futuro(1))
    calendar.guardar_gcal(ev["id"], "g-1", "2020-01-01T00:00:00Z", "e0")
    # simular edicion local "offline" (pending_push=1, recien actualizado)
    conn = calendar._conn()
    conn.execute(
        "UPDATE events SET titulo = 'Local editado', pending_push = 1, "
        "actualizado_en = datetime('now') WHERE id = ?",
        (ev["id"],),
    )
    conn.commit()
    conn.close()

    fake._events.list_response = {
        "items": [
            {
                "id": "g-1",
                "summary": "Google viejo",
                "updated": "2020-01-01T00:00:00Z",
                "start": {"dateTime": "2026-06-01T10:00:00+02:00"},
                "end": {"dateTime": "2026-06-01T11:00:00+02:00"},
            }
        ],
        "nextSyncToken": "tok",
    }
    gcal.pull_incremental()
    assert calendar.obtener_por_gcal("g-1")["titulo"] == "Local editado"


def test_sincronizar_ok(monkeypatch):
    _fake(monkeypatch)
    r = gcal.sincronizar()
    assert r["ok"] is True
    assert "pull" in r and "push" in r

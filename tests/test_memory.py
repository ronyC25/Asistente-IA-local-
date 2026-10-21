from __future__ import annotations

from src.brain.memory import SessionStore, hecho_de_texto, olvido_de_texto


def _store(tmp_path) -> SessionStore:
    return SessionStore(str(tmp_path / "memory.db"))


def test_guardar_y_cargar_turno(tmp_path):
    store = _store(tmp_path)
    store.save_turn("s1", "web", "hola", "que tal", None, [])
    data = store.load("s1", "web")
    assert data["canal"] == "web"
    assert data["mensajes"] == [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "que tal"},
    ]


def test_pending_y_ultimos_eventos(tmp_path):
    store = _store(tmp_path)
    pending = [("crear_evento", {"titulo": "X", "inicio": "2026-10-28"})]
    ultimos = [{"id": 1, "titulo": "X", "inicio": "2026-10-28"}]
    store.save_turn("s1", "telegram", "crea X", "¿Confirmas?", pending, ultimos)
    data = store.load("s1", "telegram")
    assert data["pending"] == [[n, a] for n, a in pending]
    assert data["ultimos_eventos"] == ultimos


def test_reset(tmp_path):
    store = _store(tmp_path)
    store.save_turn("s1", "web", "hola", "que tal", None, [])
    store.reset("s1")
    data = store.load("s1", "web")
    assert data["mensajes"] == []
    assert data["resumen"] is None


def test_conteo_resumen_y_limite(tmp_path):
    store = _store(tmp_path)
    for i in range(16):
        store.save_turn("s1", "web", f"u{i}", f"a{i}", None, [])
    assert store.count_messages("s1") == 32
    pendientes = store.mensajes_despues("s1", 0)
    assert len(pendientes) == 32
    store.set_summary("s1", "resumen de prueba", pendientes[20]["id"])
    data = store.load("s1", "web", limite=4)
    assert data["resumen"] == "resumen de prueba"
    assert data["resumen_hasta"] == pendientes[20]["id"]
    assert len(data["mensajes"]) == 4


def test_hechos(tmp_path):
    store = _store(tmp_path)
    h = store.add_fact("me gusta el cafe")
    assert h["valor"] == "me gusta el cafe"
    store.add_fact("me gusta el cafe")  # no duplica
    assert len(store.list_facts()) == 1
    store.add_fact("vivo en Lima")
    assert {f["valor"] for f in store.list_facts()} == {
        "me gusta el cafe",
        "vivo en Lima",
    }
    assert store.delete_fact("cafe") == 1
    assert [f["valor"] for f in store.list_facts()] == ["vivo en Lima"]
    assert store.clear_facts() == 1
    assert store.list_facts() == []


def test_extraer_comandos_de_memoria():
    assert hecho_de_texto("recuerda que me gusta el cafe") == "me gusta el cafe"
    assert hecho_de_texto("recuerdame llamar al banco") is None
    assert olvido_de_texto("olvida que me gusta el cafe") == "me gusta el cafe"
    assert olvido_de_texto("/olvida cafe") == "cafe"

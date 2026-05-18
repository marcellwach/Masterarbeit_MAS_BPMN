"""
FastAPI + Socket.IO Einstiegspunkt des Backends.

Starten:
    cd backend
    python -m uvicorn main:socket_app --host 0.0.0.0 --port 8000

Socket.IO-Events (Empfang vom Frontend):
    generate_bpmn  { prompt, session_id, existing_bpmn_xml }
        → Startet den LangGraph und gibt Statusmeldungen an den Client zurück.

Socket.IO-Events (Senden an Frontend):
    status_update      { message, iteration }  – Fortschritt während Generierung
    bpmn_result        { bpmn_xml }            – Valides + soundes BPMN bei Erfolg
    generation_failed  { reason }              – Fehlermeldung bei Nicht-Konvergenz
"""

import os
import uuid

import socketio
from dotenv import load_dotenv
from fastapi import FastAPI

from graph import build_graph, make_initial_state

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Socket.IO AsyncServer im ASGI-Modus (kompatibel mit uvicorn)
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[FRONTEND_URL]
)
app = FastAPI(title="MAS BPMN Generator")
# ASGI-App: Socket.IO wraps FastAPI – uvicorn startet socket_app, nicht app
socket_app = socketio.ASGIApp(sio, app)


@sio.on("connect")
async def on_connect(sid: str, environ: dict) -> None:
    """Neue WebSocket-Verbindung vom Frontend."""
    print(f"[socket] Client verbunden: {sid}")


@sio.on("disconnect")
async def on_disconnect(sid: str) -> None:
    """WebSocket-Verbindung getrennt (z.B. Browser-Tab geschlossen)."""
    print(f"[socket] Client getrennt: {sid}")


@sio.on("generate_bpmn")
async def handle_generate(sid: str, data: dict) -> None:
    """
    Hauptevent: empfängt Prompt und startet den LangGraph.

    Unterstützt zwei Modi:
      - create: existing_bpmn_xml ist leer → Neugenerierung
      - modify: existing_bpmn_xml vorhanden → iterative Modifikation

    Der Graph läuft vollständig async – Socket.IO kann während der
    Claude-API-Calls Statusmeldungen an den Client senden.
    """
    user_input: str = data.get("prompt", "").strip()
    session_id: str = data.get("session_id") or str(uuid.uuid4())

    if not user_input:
        await sio.emit("generation_failed",
                       {"reason": "Kein Prompt übergeben."}, to=sid)
        return

    # existing_bpmn_xml wird bei Folge-Prompts mitgeschickt (iterative Modifikation)
    existing_bpmn_xml: str = data.get("existing_bpmn_xml", "").strip()
    mode = "modify" if existing_bpmn_xml else "create"
    print(f"[generate] Session {session_id} [{mode}]: {user_input[:80]}")

    try:
        graph = build_graph(sio=sio, sid=sid, session_id=session_id)
        initial_state = make_initial_state(session_id, user_input, existing_bpmn_xml)
        # ainvoke: asynchrone Ausführung des gesamten Graphen
        await graph.ainvoke(initial_state)
    except Exception as e:
        print(f"[error] Session {session_id}: {e}")
        await sio.emit("generation_failed",
                       {"reason": f"Interner Fehler: {e}"}, to=sid)

"""
FastAPI + Socket.IO Backend – Einstiegspunkt des MAS BPMN Generators.

Start:
    cd backend
    python -m uvicorn main:socket_app --host 0.0.0.0 --port 8000

Socket.IO Events (eingehend vom Frontend):
    generate_bpmn   – startet eine Generierungssession
                      Payload: { prompt, session_id?, existing_bpmn_xml? }

Socket.IO Events (ausgehend an das Frontend):
    status_update      – Iterationsstatus (Textnachricht + Iterationsnummer)
    bpmn_result        – fertiges BPMN-XML nach erfolgreicher Validierung
    generation_failed  – Fehler-Benachrichtigung mit Begründung

HTTP-Endpunkte:
    POST /api/validate                     – BPMN-XML syntaktisch + semantisch prüfen
    GET  /api/sessions                     – alle gespeicherten Sessions auflisten
    GET  /api/export/traces/{session_id}   – einzelnen Trace-Log als JSON exportieren
    GET  /api/export/traces                – alle Trace-Logs als ZIP exportieren
    GET  /api/export/report                – Auswertungsbericht (GZ1/GZ2/GZ4) als JSON
    GET  /api/export/bpmn/{session_id}     – finales BPMN-XML als .bpmn-Datei
"""

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import socketio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from graph import build_graph, make_initial_state
from language_interface.bpmn import BpmnLanguageInterface

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")
LOG_DIR = Path(os.getenv("LOG_DIR", "traces"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
app = FastAPI(title="MAS BPMN Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

socket_app = socketio.ASGIApp(sio, app)


@sio.on("connect")
async def on_connect(sid: str, environ: dict) -> None:
    print(f"[socket] Client verbunden: {sid}")


@sio.on("disconnect")
async def on_disconnect(sid: str) -> None:
    print(f"[socket] Client getrennt: {sid}")


@sio.on("generate_bpmn")
async def handle_generate(sid: str, data: dict) -> None:
    """
    Startet eine vollständige BPMN-Generierungssession über den LangGraph.

    Der Graph läuft asynchron: coordinator_init → generator → validator → coordinator_eval.
    Statusmeldungen werden während der Ausführung per status_update an den Client gesendet.
    Ergebnis kommt als bpmn_result (Erfolg) oder generation_failed (Fehler/Limit).
    """
    user_input: str = data.get("prompt", "").strip()
    session_id: str = data.get("session_id") or str(uuid.uuid4())

    if not user_input:
        await sio.emit("generation_failed", {"reason": "Kein Prompt übergeben."}, to=sid)
        return

    existing_bpmn_xml: str = data.get("existing_bpmn_xml", "").strip()
    mode = "modify" if existing_bpmn_xml else "create"
    print(f"[generate] Session {session_id} [{mode}]: {user_input[:80]}")

    try:
        graph = build_graph(sio=sio, sid=sid, session_id=session_id)
        initial_state = make_initial_state(session_id, user_input, existing_bpmn_xml)
        await graph.ainvoke(initial_state)
    except Exception as e:
        print(f"[error] Session {session_id}: {e}")
        await sio.emit("generation_failed", {"reason": f"Interner Fehler: {e}"}, to=sid)


# socket.io setzt intern allow-methods: GET, was den Browser-Preflight für POST blockiert
@app.options("/api/validate")
async def options_validate(request: Request):
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": FRONTEND_URL,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "600",
        }
    )


class ValidateRequest(BaseModel):
    xml: str
    label: str = ""


@app.post("/api/validate")
async def validate_bpmn(req: ValidateRequest):
    """
    Führt eine vollständige Validierung eines BPMN-XML-Strings durch.

    Schritt 1: Syntaxprüfung via lxml + XSD-Schema + Referenzintegrität.
    Schritt 2: Soundness-Prüfung via pm4py/Woflan (synchron, läuft im Thread-Pool).
    Timeout nach 25s – bei sehr komplexen Modellen wird Woflan übersprungen.

    Gibt Violations gruppiert nach Typ, XML-Statistiken und eine lesbare Summary zurück.
    """
    import time
    if not req.xml.strip():
        raise HTTPException(status_code=400, detail="Kein XML übergeben.")

    li = BpmnLanguageInterface()
    start = time.time()
    # Woflan blockiert synchron → Thread-Pool damit der Event Loop frei bleibt
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, li.validate, req.xml),
            timeout=25.0
        )
    except asyncio.TimeoutError:
        from models.feedback import ErrorType, ValidationResult, Violation
        from datetime import datetime, timezone
        result = ValidationResult(
            is_valid=True,
            is_sound=False,
            violations=[Violation(
                error_type=ErrorType.SEMANTIC_SOUNDNESS,
                affected_elements=[],
                description="Soundness-Prüfung übersprungen: Modell zu komplex für Woflan (Timeout nach 25s). Bitte Modell vereinfachen."
            )],
            validation_timestamp=datetime.now(timezone.utc).isoformat()
        )
    elapsed = round(time.time() - start, 3)

    # Violations nach Typ gruppieren
    syntax_violations = [v for v in result.violations if v.error_type.value.startswith("syntax")]
    semantic_violations = [v for v in result.violations if v.error_type.value.startswith("semantic")]

    # Auswertung und Empfehlungen
    summary_lines = []
    if result.is_valid and result.is_sound:
        summary_lines.append("✓ Das BPMN-Modell ist syntaktisch korrekt und semantisch sound.")
    else:
        if not result.is_valid:
            summary_lines.append(f"✗ Syntaxfehler: {len(syntax_violations)} Verletzung(en) gefunden.")
            for v in syntax_violations:
                elems = ", ".join(v.affected_elements) or "—"
                summary_lines.append(f"  [{v.error_type.value}] Elemente: {elems} – {v.description}")
        if not result.is_sound:
            summary_lines.append(f"✗ Soundness-Fehler: {len(semantic_violations)} Verletzung(en) gefunden.")
            for v in semantic_violations:
                summary_lines.append(f"  [{v.error_type.value}] {v.description}")

    # Statistiken aus dem XML (für das Frontend-Dashboard)
    from lxml import etree
    xml_stats = {}
    try:
        root = etree.fromstring(req.xml.encode("utf-8"))
        ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"
        xml_stats = {
            "start_events": len(list(root.iter(f"{{{ns}}}startEvent"))),
            "end_events": len(list(root.iter(f"{{{ns}}}endEvent"))),
            "tasks": len(list(root.iter(f"{{{ns}}}task"))) +
                     len(list(root.iter(f"{{{ns}}}userTask"))) +
                     len(list(root.iter(f"{{{ns}}}serviceTask"))) +
                     len(list(root.iter(f"{{{ns}}}scriptTask"))),
            "gateways": len(list(root.iter(f"{{{ns}}}exclusiveGateway"))) +
                        len(list(root.iter(f"{{{ns}}}parallelGateway"))) +
                        len(list(root.iter(f"{{{ns}}}inclusiveGateway"))),
            "sequence_flows": len(list(root.iter(f"{{{ns}}}sequenceFlow"))),
            "has_di": "<bpmndi:BPMNDiagram" in req.xml or "BPMNDiagram" in req.xml,
        }
    except Exception:
        pass

    return {
        "label": req.label,
        "is_valid": result.is_valid,
        "is_sound": result.is_sound,
        "validation_timestamp": result.validation_timestamp,
        "duration_seconds": elapsed,
        "xml_stats": xml_stats,
        "violations": [v.model_dump() for v in result.violations],
        "syntax_violations_count": len(syntax_violations),
        "semantic_violations_count": len(semantic_violations),
        "summary": summary_lines,
    }


@app.get("/api/sessions")
async def list_sessions():
    """Listet alle gespeicherten Sessions mit Status-Kurzübersicht (aus Trace-Logs)."""
    sessions = []
    for path in sorted(LOG_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            process = data.get("process_entry") or {}
            sessions.append({
                "session_id": data.get("session_id"),
                "user_input": data.get("user_input", "")[:100],
                "total_iterations": process.get("total_iterations"),
                "termination_reason": process.get("termination_reason"),
                "final_status": process.get("final_status"),
                "timestamp": process.get("timestamp"),
                "has_bpmn": bool(data.get("final_bpmn_xml")),
            })
        except Exception:
            pass
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/export/traces/{session_id}")
async def export_single_trace(session_id: str):
    """Gibt den vollständigen Drei-Ebenen-Trace-Log einer Session als JSON zurück."""
    path = LOG_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/export/traces")
async def export_all_traces():
    """Exportiert alle Trace-Logs als ZIP-Archiv (mas_bpmn_traces.zip)."""
    trace_files = list(LOG_DIR.glob("*.json"))
    if not trace_files:
        raise HTTPException(status_code=404, detail="Keine Trace-Logs vorhanden")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in trace_files:
            zf.write(path, arcname=f"traces/{path.name}")

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=mas_bpmn_traces.zip"}
    )


@app.get("/api/export/report")
async def export_evaluation_report():
    """
    Berechnet den Auswertungsbericht über alle gespeicherten Sessions.

    Metriken:
        GZ1 – Syntaktische Konformitätsrate (Zielwert: 1.0, garantiert durch DP2)
        GZ2 – Semantische Korrektheit: Konvergenzrate + Soundness-Rate
        GZ4 – Traceability-Vollständigkeit (Zielwert: 1.0, garantiert durch DP4)
    """
    trace_files = list(LOG_DIR.glob("*.json"))
    if not trace_files:
        raise HTTPException(status_code=404, detail="Keine Trace-Logs vorhanden")

    logs = []
    for path in trace_files:
        try:
            logs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass

    # GZ1: Syntaktische Konformität (Zielwert: 1.0 – durch DP2 strukturell garantiert)
    # Berechnung: validation_entries[type="syntax"].passed / total
    total_syntax, passed_syntax = 0, 0
    for log in logs:
        for entry in log.get("validation_entries", []):
            if entry.get("validation_type") == "syntax":
                total_syntax += 1
                if entry.get("passed"):
                    passed_syntax += 1

    # GZ2: Semantische Korrektheit – Konvergenzrate + Soundness-Rate nach Feedback-Schleife (DP3)
    # Berechnung: process_entry.termination_reason=="success" / total_sessions
    total_sessions = len(logs)
    success_sessions = sum(
        1 for log in logs
        if (log.get("process_entry") or {}).get("termination_reason") == "success"
    )
    sound_sessions = sum(
        1 for log in logs
        if (log.get("process_entry") or {}).get("final_status") == "valid_and_sound"
    )

    # GZ4: Traceability-Vollständigkeit (Zielwert: 1.0 – durch DP4 strukturell garantiert)
    # Berechnung: Sessions mit allen drei Log-Ebenen (output + validation + process) / total
    complete_logs = sum(
        1 for log in logs
        if log.get("output_entries")
        and log.get("validation_entries")
        and log.get("process_entry")
    )

    # Iterationsstatistik
    iterations = [
        (log.get("process_entry") or {}).get("total_iterations", 0)
        for log in logs
        if (log.get("process_entry") or {}).get("termination_reason") == "success"
    ]

    def rate(n, d): return round(n / d, 4) if d > 0 else None

    # GZ3 (Rollenbasierte Architektur) ist keine messbare Metrik – struktureller Nachweis
    # durch Code-Analyse: generator.py enthält keinen Validator-Aufruf,
    # validator.py enthält keinen anthropic-Import, coordinator.py erzeugt kein BPMN-XML.

    report = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "sessions_evaluated": total_sessions,
        "gz1_syntactic_conformance": {
            "description": "Anteil syntaktisch valider Outputs (Zielwert: 1.0 durch DP2)",
            "total_syntax_checks": total_syntax,
            "passed": passed_syntax,
            "rate": rate(passed_syntax, total_syntax),
            "target": 1.0,
        },
        "gz2_semantic_correctness": {
            "description": "Soundness-Rate und Konvergenzrate nach Feedback-Schleife",
            "total_sessions": total_sessions,
            "converged_sessions": success_sessions,
            "sound_sessions": sound_sessions,
            "convergence_rate": rate(success_sessions, total_sessions),
            "soundness_rate": rate(sound_sessions, total_sessions),
        },
        "gz4_traceability": {
            "description": "Vollständigkeit der Logs (alle drei Ebenen vorhanden, Zielwert: 1.0)",
            "total_sessions": total_sessions,
            "complete_logs": complete_logs,
            "completeness_rate": rate(complete_logs, total_sessions),
            "target": 1.0,
        },
        "iterations": {
            "description": "Iterationszahl bis zur Konvergenz (nur erfolgreiche Sessions)",
            "samples": len(iterations),
            "avg": round(sum(iterations) / len(iterations), 2) if iterations else None,
            "min": min(iterations) if iterations else None,
            "max": max(iterations) if iterations else None,
        },
    }

    return JSONResponse(content=report)


@app.get("/api/export/bpmn/{session_id}")
async def export_bpmn(session_id: str):
    """Gibt das finale BPMN-XML einer Session als herunterladbare .bpmn-Datei zurück."""
    path = LOG_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden")

    data = json.loads(path.read_text(encoding="utf-8"))
    bpmn_xml = data.get("final_bpmn_xml")
    if not bpmn_xml:
        raise HTTPException(status_code=404, detail="Session enthält kein finales BPMN-XML")

    return StreamingResponse(
        io.StringIO(bpmn_xml),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={session_id}.bpmn"}
    )


# StaticFiles muss nach allen API-Routen stehen – sonst fängt "/" alle Requests ab
from fastapi.staticfiles import StaticFiles
_frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'out')
if os.path.exists(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

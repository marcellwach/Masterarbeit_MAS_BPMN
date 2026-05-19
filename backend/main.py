"""
FastAPI + Socket.IO Einstiegspunkt des Backends.

Starten:
    cd backend
    python -m uvicorn main:socket_app --host 0.0.0.0 --port 8000

Socket.IO-Events (Empfang vom Frontend):
    generate_bpmn  { prompt, session_id, existing_bpmn_xml }

Socket.IO-Events (Senden an Frontend):
    status_update      { message, iteration }
    bpmn_result        { bpmn_xml }
    generation_failed  { reason }

HTTP-Endpunkte (für Evaluation/Export):
    GET  /api/export/report         → JSON-Evaluationsbericht (GZ1/GZ2/GZ4)
    GET  /api/export/traces         → ZIP aller Trace-Logs
    GET  /api/export/traces/{id}    → einzelner Trace-Log als JSON
    GET  /api/sessions              → Liste aller Sessions mit Kurzinfo
    POST /api/validate              → Syntax + Soundness-Prüfung für beliebiges BPMN-XML
"""

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import socketio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from graph import build_graph, make_initial_state
from language_interface.bpmn import BpmnLanguageInterface

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
LOG_DIR = Path(os.getenv("LOG_DIR", "traces"))

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[FRONTEND_URL])
app = FastAPI(title="MAS BPMN Generator")

# CORS für HTTP-Endpunkte (Frontend auf localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_methods=["GET"],
    allow_headers=["*"],
)

socket_app = socketio.ASGIApp(sio, app)


# ---------------------------------------------------------------------------
# Socket.IO Events
# ---------------------------------------------------------------------------

@sio.on("connect")
async def on_connect(sid: str, environ: dict) -> None:
    print(f"[socket] Client verbunden: {sid}")


@sio.on("disconnect")
async def on_disconnect(sid: str) -> None:
    print(f"[socket] Client getrennt: {sid}")


@sio.on("generate_bpmn")
async def handle_generate(sid: str, data: dict) -> None:
    """Empfängt Prompt und startet den LangGraph (create oder modify)."""
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


# ---------------------------------------------------------------------------
# HTTP-Endpunkte für Export, Evaluation und Validierung
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    xml: str
    label: str = ""   # Optionale Bezeichnung (z.B. "GPT-4o Versuch 1")


@app.post("/api/validate")
async def validate_bpmn(req: ValidateRequest):
    """
    Führt vollständige Syntax- und Soundness-Prüfung für beliebiges BPMN-XML durch.
    Kann für jedes LLM genutzt werden – einfach das generierte XML einfügen.

    Rückgabe:
      - is_valid:   XML-Wohlgeformtheit + Referenzintegrität
      - is_sound:   Woflan-Soundness (Petri-Netz-Mapping)
      - violations: Liste typisierter Fehler mit Beschreibung
      - summary:    Auswertung mit Empfehlungen
    """
    import time
    if not req.xml.strip():
        raise HTTPException(status_code=400, detail="Kein XML übergeben.")

    li = BpmnLanguageInterface()
    start = time.time()
    result = li.validate(req.xml)
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

    # Statistiken aus dem XML
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
    """
    Gibt eine Liste aller abgeschlossenen Sessions zurück.
    Enthält session_id, user_input, Iterationszahl und finalen Status.
    """
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
    """Gibt den vollständigen Trace-Log einer Session als JSON zurück."""
    path = LOG_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' nicht gefunden")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/export/traces")
async def export_all_traces():
    """
    Gibt alle Trace-Logs als ZIP-Archiv zurück.
    Enthält: alle {session_id}.json Dateien aus dem traces/-Verzeichnis.
    """
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
    Berechnet den Evaluationsbericht (GZ1/GZ2/GZ4) aus allen Trace-Logs
    und gibt ihn als JSON zurück.

    GZ1 – Syntaktische Konformität (Anteil valider Syntax-Checks)
    GZ2 – Semantische Korrektheit (Soundness-Rate + Konvergenzrate)
    GZ4 – Traceability-Vollständigkeit (alle drei Log-Ebenen vorhanden)
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

    # GZ1: Syntaktische Konformität
    total_syntax, passed_syntax = 0, 0
    for log in logs:
        for entry in log.get("validation_entries", []):
            if entry.get("validation_type") == "syntax":
                total_syntax += 1
                if entry.get("passed"):
                    passed_syntax += 1

    # GZ2: Semantische Korrektheit
    total_sessions = len(logs)
    success_sessions = sum(
        1 for log in logs
        if (log.get("process_entry") or {}).get("termination_reason") == "success"
    )
    sound_sessions = sum(
        1 for log in logs
        if (log.get("process_entry") or {}).get("final_status") == "valid_and_sound"
    )

    # GZ4: Traceability-Vollständigkeit
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
    """Gibt das finale BPMN-XML einer Session als .bpmn-Datei zurück."""
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

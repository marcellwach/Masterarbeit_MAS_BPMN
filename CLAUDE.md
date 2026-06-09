# MAS BPMN Generator – Projektkontext für Claude

## Überblick

Multi-Agenten-System (MAS) zur KI-gestützten Generierung von BPMN-2.0-Prozessmodellen.
Masterarbeit von Marcell Wach. Stack: Python 3.12 / FastAPI / LangGraph / Anthropic Claude + Next.js 14.

## Architektur

```
Nutzereingabe (Chat)
  → Generator-Agent   (Claude tool_use → JSON → BPMN-XML)
  → Validator-Agent   (lxml XSD-Check + pm4py Woflan, kein LLM)
  → Koordinator-Agent (Feedback-Schleife, max 5 Iterationen)
  → bpmn_result Event → bpmn-js Frontend-Renderer
```

Design-Prinzipien: DP1 (kein LLM für Validierung), DP2 (tool_use als struktureller Constraint),
DP3 (Feedback-Schleife), DP4 (drei-Ebenen Tracing), DP5 (abstraktes LanguageInterface).

## Lokaler Start

**Entwicklung (Hot-Reload, empfohlen):**
```
Rechtsklick start-local.ps1 → "Mit PowerShell ausführen"
→ Backend auf localhost:8000, Frontend auf localhost:3000
```

**Einzelner Terminal (kein Hot-Reload):**
```
cd backend
python launcher.py
→ localhost:8000 (Frontend als statisches Export eingebettet, wenn frontend/out/ existiert)
```

## Ports & Verbindungen

- Backend: `localhost:8000` (FastAPI + Socket.IO + optionale StaticFiles)
- Frontend-Dev: `localhost:3000` (next dev, verbindet sich via Socket.IO zu :8000)
- Socket.IO-URL ist hardcoded auf `http://localhost:8000` im Frontend

## Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `backend/main.py` | FastAPI-App, Socket.IO-Events, API-Endpunkte |
| `backend/graph.py` | LangGraph-Zustandsmaschine |
| `backend/agents/generator.py` | Claude tool_use, Prompt-Logik |
| `backend/agents/validator.py` | Woflan + XSD-Validierung |
| `backend/agents/coordinator.py` | Iterationssteuerung, Socket-Events |
| `backend/language_interface/bpmn.py` | BPMN-Schema, Validierung, JSON→XML |
| `backend/traces/` | Session-Trace-Logs (UUID.json) |
| `frontend/app/page.tsx` | Haupt-UI (Chat + BPMN-Viewer) |
| `frontend/components/` | ChatPanel, BpmnViewer, ExportBar, DebugPanel |
| `evaluation/evaluate.py` | GZ1/GZ2/GZ4 Metriken aus Traces berechnen |

## Konfiguration (.env)

```
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-sonnet-4-6
TEMPERATURE=0.0
MAX_ITERATIONS=5
LOG_DIR=traces
FRONTEND_URL=http://localhost:8000
```

## Evaluation ausführen

```
cd backend
python ..\evaluation\evaluate.py --traces-dir traces\ --output ..\evaluation\report.json
```

## Known Limitations

- **Swimlanes/Pools**: Nicht unterstützt (bpmn-auto-layout Fehler bei attachedToRef)
- **XSD multi-file**: BPMN-2.0-XSD referenziert externe Dateien, nur Haupt-XSD wird geprüft
- **Woflan auf Windows**: Nach gewaltsamen Prozessabbrüchen (`Stop-Process -Force`) kann pm4py
  eine stale PID cachen → Fix in `bpmn.py`: automatischer Retry via `ProcessPoolExecutor`
- **Komplexe Modelle**: Woflan-Analyse kann bei sehr großen Petri-Netzen sehr lange dauern

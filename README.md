# Masterarbeit_MAS_BPMN

**Multi-Agenten-System zur KI-gestützten BPMN-2.0-Generierung**

Implementierung zur Masterarbeit in Wirtschaftsinformatik:
> *Designprinzipien für Multi-Agenten-Systeme zur KI-gestützten Modellierung auf Basis formaler Sprachen am Beispiel von BPMN 2.0*

---

## Überblick

Das System generiert aus einer natürlichsprachlichen Prozessbeschreibung automatisch ein syntaktisch korrektes und semantisch soundes BPMN-2.0-Modell. Es setzt fünf wissenschaftlich hergeleitete Designprinzipien (DP1–DP5) um.

```
Nutzer gibt Prozessbeschreibung ein
          ↓
    [Generator-Agent]  ←──────────────────────────┐
    Claude Sonnet 4.6                             │
    tool_use → JSON → XML (DP2)                   │
          ↓                                       │
    [Validator-Agent]                             │
    lxml: XSD-Syntaxcheck                         │
    pm4py: Woflan Soundness-Check (DP1)           │
          ↓                                       │
    [Koordinator-Agent]                           │
    Valide & Sound? → BPMN anzeigen         Nein →┘
                    → Trace-Log schreiben (DP4)
```

---

## Designprinzipien

| # | Prinzip | Umsetzung |
|---|---------|-----------|
| DP1 | Rollenbasierte Agentenspezialisierung | Generator, Validator, Koordinator als getrennte LangGraph-Nodes |
| DP2 | Constraint-gesteuerte Generierung | Anthropic `tool_use` mit JSON-Schema erzwingt strukturkonformen Output |
| DP3 | Iteratives Feedback-basiertes Refinement | LangGraph conditional edge, typisierte `Violation`-Objekte als Feedback |
| DP4 | Traceability | Drei-Ebenen-Logging (Ausgabe, Validierung, Prozess) als JSON |
| DP5 | Sprachunabhängige Generalisierbarkeit | Abstrakte `LanguageInterface`-Basisklasse |

---

## Architektur

```
frontend/                      # Next.js 14 + bpmn-js
├── app/
│   ├── page.tsx               # Haupt-Layout, Socket.IO-Client, Modifikationsmodus
│   └── validate/page.tsx      # Standalone-Validator für beliebige LLM-Outputs
└── components/
    ├── ChatPanel.tsx          # Eingabe + Statusmeldungen
    ├── BpmnViewer.tsx         # bpmn-js Viewer/Editor + bpmn-auto-layout
    ├── ExportBar.tsx          # Import/Export XML/SVG, Manuell-Modus, Eval-Export
    └── DebugPanel.tsx         # Entwickler-Debug-Overlay (nur dev)

backend/                       # FastAPI + LangGraph + Anthropic
├── main.py                    # FastAPI + Socket.IO Server + HTTP-Endpunkte
├── graph.py                   # LangGraph StateGraph
├── agents/
│   ├── generator.py           # DP1+DP2: BPMN-Generierung via Claude tool_use
│   ├── validator.py           # DP1: lxml + pm4py/Woflan, kein LLM
│   └── coordinator.py        # DP1+DP3+DP4: Orchestrierung + Socket.IO-Events
├── language_interface/
│   ├── base.py                # DP5: Abstrakte Basisklasse
│   └── bpmn.py                # BPMN-2.0-Implementierung
├── models/
│   ├── feedback.py            # Pydantic: ValidationResult, Violation, ErrorType
│   ├── trace.py               # Pydantic: TraceLog, OutputTraceEntry, ...
│   └── state.py               # LangGraph AgentState (TypedDict)
└── trace_logger/
    └── logger.py              # DP4: Drei-Ebenen-Logger

evaluation/
└── evaluate.py                # Metrik-Berechnung GZ1/GZ2/GZ4 (CLI)
```

---

## Quickstart

### Voraussetzungen
- Python 3.12+
- Node.js 18+
- Anthropic API Key

### Backend starten

```bash
cd backend
pip install -r requirements.txt

# .env anlegen (Vorlage: .env.example)
copy ..\.env.example ..\.env
# ANTHROPIC_API_KEY in .env eintragen
```

**Windows (PowerShell):**
```powershell
# Backend als Windows-Prozess starten (nicht per Bash – pkill kann Windows-Prozesse nicht killen)
Set-Location backend
python -m uvicorn main:socket_app --host 0.0.0.0 --port 8000
```

### Frontend starten

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Evaluation

```bash
# Nach mehreren Generierungen:
python evaluation/evaluate.py --traces-dir traces/ --output report.json
```

Berechnet:
- **GZ1** – Syntaktische Konformität (Zielwert: 100% durch DP2)
- **GZ2** – Semantische Korrektheit / Soundness-Rate nach Feedback-Schleife
- **GZ4** – Traceability-Vollständigkeit (alle drei Log-Ebenen)

---

## Technische Entscheidungen

### DP2: tool_use statt Outlines

Technischer PoC ergab: Outlines 1.3.0 unterstützt keine structured generation mit der Anthropic API (`NotImplementedError`). Als gleichwertiger Mechanismus wird Anthropics `tool_use` mit JSON-Schema genutzt – der Constraint greift API-seitig und garantiert schema-konformen Output.

### Soundness-Prüfung

BPMN-XML → Petri-Netz (pm4py, Dijkman et al. 2008) → Woflan-Algorithmus prüft:
1. Erreichbarkeit des Endzustands
2. Deadlock-Freiheit
3. Keine toten Transitionen

Bewusst **kein LLM** für Validierung (DP1: Self-Preference Bias vermeiden).

### Iterative Modifikation

Das Frontend sendet bei Folge-Prompts das bestehende BPMN-XML mit. Claude erhält es als Kontext und modifiziert das Modell gezielt, ohne es neu zu generieren.

---

## HTTP-Endpunkte (Backend)

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| `POST` | `/api/validate` | Syntax + Soundness für beliebiges BPMN-XML (Baseline-Evaluation) |
| `GET` | `/api/export/report` | GZ1/GZ2/GZ4-Metriken aus allen Trace-Logs |
| `GET` | `/api/export/traces` | ZIP aller Trace-Logs |
| `GET` | `/api/export/traces/{id}` | Einzelner Trace-Log als JSON |
| `GET` | `/api/export/bpmn/{id}` | BPMN-XML einer Session |
| `GET` | `/api/sessions` | Sessionliste mit Kurzinfo |

---

## Known Limitations

1. **XSD-Validierung**: Nur Wohlgeformtheit + Referenzintegrität (OMG BPMN 2.0 XSD ist multi-file, nicht direkt ladbar)
2. **Swimlanes/Pools**: Nicht unterstützt – `bpmn-auto-layout` verarbeitet BPMN-Collaboration-Strukturen nicht korrekt (`attachedToRef`-Bug). Gilt als Stand der Technik auch für andere Tools.
3. **Woflan: Mehrere Start-/End-Events**: Woflan setzt ein Workflow-Netz mit **genau einem Start-Event und einem End-Event** voraus. BPMN 2.0 erlaubt mehrere Start-/Endevents, aber das BPMN→Petri-Netz-Mapping (pm4py, Dijkman et al. 2008) erzeugt dabei mehrere Quell-/Senkenplätze. Woflan verweigert die Prüfung mit „more than one source/sink place" – der Validator meldet dies explizit. Der Generator ist auf ein Start- und ein End-Event ausgelegt und ist davon nicht betroffen.
4. **Random Seed**: Anthropic API unterstützt keinen Seed-Parameter
5. **Baseline-Vergleich**: Monolithisches System und GPT-4o-Vergleich nicht implementiert
6. **Wiederholungen**: 3x-Wiederholung pro Testszenario nicht automatisiert

---

## Konfiguration (.env)

```env
ANTHROPIC_API_KEY=...        # Anthropic API Key
CLAUDE_MODEL=claude-sonnet-4-6
TEMPERATURE=0.0              # 0.0 für maximale Konsistenz
MAX_ITERATIONS=5             # Maximale Feedback-Iterationen
LOG_DIR=traces/              # Verzeichnis für Trace-Logs
FRONTEND_URL=http://localhost:3000
```

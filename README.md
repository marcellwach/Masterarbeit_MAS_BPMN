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
    Claude Sonnet 4.6                              │
    tool_use → JSON → XML (DP2)                    │
          ↓                                        │
    [Validator-Agent]                              │
    lxml: XSD-Syntaxcheck                          │
    pm4py: Woflan Soundness-Check (DP1)            │
          ↓                                        │
    [Koordinator-Agent]                            │
    Valide & Sound? → BPMN anzeigen          Nein →┘
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
frontend/                      # Next.js + bpmn-js
├── app/page.tsx               # Haupt-Layout, Socket.IO-Client
└── components/
    ├── ChatPanel.tsx          # Eingabe + Statusmeldungen
    ├── BpmnViewer.tsx         # bpmn-js Viewer + bpmn-auto-layout
    └── DebugPanel.tsx         # Entwickler-Debug-Overlay (nur dev)

backend/                       # FastAPI + LangGraph
├── main.py                    # FastAPI + Socket.IO Server
├── graph.py                   # LangGraph StateGraph
├── agents/
│   ├── generator.py           # DP1+DP2: BPMN-Generierung via Claude
│   ├── validator.py           # DP1: lxml + pm4py, kein LLM
│   └── coordinator.py        # DP1+DP3+DP4: Orchestrierung
├── language_interface/
│   ├── base.py                # DP5: Abstrakte Basisklasse
│   └── bpmn.py                # BPMN-2.0-Implementierung
├── models/
│   ├── feedback.py            # Pydantic: ValidationResult, Violation
│   ├── trace.py               # Pydantic: TraceLog-Modelle
│   └── state.py               # LangGraph AgentState
└── trace_logger/
    └── logger.py              # DP4: Drei-Ebenen-Logger

evaluation/
└── evaluate.py                # Metrik-Berechnung GZ1/GZ2/GZ4

poc/
└── test_outlines_anthropic.py # Technische Risikovalidierung DP2
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
cp ../.env.example ../.env
# ANTHROPIC_API_KEY in .env eintragen

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

Technischer PoC (`poc/test_outlines_anthropic.py`) ergab: Outlines 1.3.0 unterstützt keine structured generation mit der Anthropic API (`NotImplementedError`). Als gleichwertiger Mechanismus wird Anthropics `tool_use` mit JSON-Schema genutzt – der Constraint greift API-seitig und garantiert schema-konformen Output.

### Soundness-Prüfung

BPMN-XML → Petri-Netz (pm4py, Dijkman et al. 2008) → Woflan-Algorithmus prüft:
1. Erreichbarkeit des Endzustands
2. Deadlock-Freiheit
3. Keine toten Transitionen

Bewusst **kein LLM** für Validierung (DP1: Self-Preference Bias vermeiden).

### Iterative Modifikation

Das Frontend sendet bei Folge-Prompts das bestehende BPMN-XML mit. Claude erhält es als Kontext und modifiziert das Modell gezielt, ohne es neu zu generieren.

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

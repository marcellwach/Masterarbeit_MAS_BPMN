"""
BPMN-2.0-Implementierung der LanguageInterface-Basisklasse (DP5).

Implementiert alle vier abstrakten Methoden für die Zielsprache BPMN 2.0:

  get_tool_schema()   → BPMN-JSON-Schema für Anthropic tool_use (DP2)
  get_system_prompt() → BPMN-Experten-Prompt für den Generator-Agent
  json_to_output()    → Deterministischer JSON → BPMN-XML Konverter
  validate()          → lxml (XSD-Syntax) + pm4py/Woflan (Soundness)

Validierung in zwei Stufen:
  1. Syntaxvalidierung (lxml):
     - XML-Wohlgeformtheit
     - XSD-Konformität gegen OMG BPMN 2.0 Schema (sofern vorhanden)
     - Referenzintegrität (sourceRef/targetRef zeigen auf existierende IDs)

  2. Soundness-Prüfung (pm4py + Woflan):
     - BPMN → Petri-Netz Mapping (Dijkman et al. 2008)
     - Woflan prüft: Erreichbarkeit, Deadlock-Freiheit, keine toten Transitionen

Layout:
  Das Backend generiert kein DI (Diagram Interchange). Das visuelle Layout
  wird vollständig von bpmn-auto-layout im Frontend übernommen.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lxml import etree
from models.feedback import ErrorType, ValidationResult, Violation
from language_interface.base import LanguageInterface

# Pfad zur BPMN-2.0-XSD (optional – für erweiterte Syntaxvalidierung)
GRAMMAR_DIR = Path(__file__).parent.parent / "grammar"
XSD_PATH = GRAMMAR_DIR / "bpmn20.xsd"

# BPMN-2.0-Namespaces für lxml-Verarbeitung
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"

# tool_use JSON-Schema – definiert die BPMN-Struktur die Claude erzeugen muss (DP2)
BPMN_TOOL_SCHEMA = {
    "name": "generate_bpmn",
    "description": (
        "Generiert ein BPMN 2.0 Prozessmodell als strukturiertes JSON. "
        "Alle IDs müssen eindeutig sein. Jede sequence_flow muss source_ref und target_ref "
        "auf existierende Element-IDs verweisen. Jedes Element ausser startEvent und endEvent "
        "muss mindestens eine incoming und eine outgoing Verbindung haben."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "process_id": {"type": "string"},
            "process_name": {"type": "string"},
            "start_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["id", "name"]
                }
            },
            "end_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["id", "name"]
                }
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["id", "name"]
                }
            },
            "gateways": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["exclusiveGateway", "parallelGateway", "inclusiveGateway"]
                        }
                    },
                    "required": ["id", "name", "type"]
                }
            },
            "sequence_flows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "source_ref": {"type": "string"},
                        "target_ref": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["id", "source_ref", "target_ref"]
                }
            }
        },
        "required": [
            "process_id", "process_name",
            "start_events", "end_events", "tasks", "sequence_flows"
        ]
    }
}


class BpmnLanguageInterface(LanguageInterface):

    def get_tool_schema(self) -> dict:
        return BPMN_TOOL_SCHEMA

    def get_system_prompt(self) -> str:
        return """Du bist ein BPMN-2.0-Experte. Deine Aufgabe ist es, aus einer natürlichsprachlichen
Prozessbeschreibung ein korrektes BPMN-2.0-Modell zu generieren.

Regeln die du IMMER einhalten musst:
- Jede ID muss eindeutig sein (z.B. StartEvent_1, Task_1, Gateway_1, EndEvent_1, Flow_1)
- Jede sequence_flow muss auf existierende Element-IDs verweisen
- Jedes Task und Gateway braucht mindestens eine incoming UND eine outgoing Flow
- startEvent hat nur outgoing, endEvent nur incoming Flows
- Nutze exclusiveGateway für Entweder-oder-Entscheidungen
- Nutze parallelGateway wenn Aktivitäten parallel ausgeführt werden
- Der Prozess muss vom startEvent zum endEvent vollständig durchgängig sein (kein Dead-End)

Wenn du Feedback zu Fehlern erhältst, beachte die affected_elements und korrigiere gezielt diese Elemente."""

    def json_to_output(self, data: dict) -> str:
        """Deterministischer JSON → BPMN-XML Konverter (kein LLM-Aufruf).
        Kein DI – Layout wird vollständig von bpmn-auto-layout im Frontend übernommen."""
        flows = data.get("sequence_flows", [])

        def incoming_flows(eid):
            return [f["id"] for f in flows if f["target_ref"] == eid]

        def outgoing_flows(eid):
            return [f["id"] for f in flows if f["source_ref"] == eid]

        def flow_refs(eid, direction):
            tag = "incoming" if direction == "in" else "outgoing"
            ids = incoming_flows(eid) if direction == "in" else outgoing_flows(eid)
            return "".join(f"<{tag}>{fid}</{tag}>" for fid in ids)

        # Prozess-Elemente
        elements = []
        for se in data.get("start_events", []):
            elements.append(
                f'<startEvent id="{se["id"]}" name="{_esc(se["name"])}">'
                f'{flow_refs(se["id"], "out")}</startEvent>'
            )
        for task in data.get("tasks", []):
            elements.append(
                f'<task id="{task["id"]}" name="{_esc(task["name"])}">'
                f'{flow_refs(task["id"], "in")}{flow_refs(task["id"], "out")}</task>'
            )
        for gw in data.get("gateways", []):
            # isMarkerVisible gehört ins DI (BPMNShape), nicht ins Prozess-Element
            gw_type = gw.get("type", "exclusiveGateway")
            elements.append(
                f'<{gw_type} id="{gw["id"]}" name="{_esc(gw["name"])}">'
                f'{flow_refs(gw["id"], "in")}{flow_refs(gw["id"], "out")}</{gw_type}>'
            )
        for ee in data.get("end_events", []):
            elements.append(
                f'<endEvent id="{ee["id"]}" name="{_esc(ee["name"])}">'
                f'{flow_refs(ee["id"], "in")}</endEvent>'
            )
        for flow in flows:
            name_attr = f' name="{_esc(flow["name"])}"' if flow.get("name") else ""
            elements.append(
                f'<sequenceFlow id="{flow["id"]}" '
                f'sourceRef="{flow["source_ref"]}" '
                f'targetRef="{flow["target_ref"]}"{name_attr}/>'
            )

        # Auto-Layout: Positionen berechnen
        positions = _compute_layout(data)

        # DI-Shapes generieren
        di_shapes = []
        for se in data.get("start_events", []):
            p = positions.get(se["id"], {"x": 100, "y": 200, "w": 36, "h": 36})
            di_shapes.append(
                f'<bpmndi:BPMNShape id="{se["id"]}_di" bpmnElement="{se["id"]}">\n'
                f'  <dc:Bounds x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}"/>\n'
                f'  <bpmndi:BPMNLabel/>\n'
                f'</bpmndi:BPMNShape>'
            )
        for task in data.get("tasks", []):
            p = positions.get(task["id"], {"x": 200, "y": 170, "w": 100, "h": 80})
            di_shapes.append(
                f'<bpmndi:BPMNShape id="{task["id"]}_di" bpmnElement="{task["id"]}">\n'
                f'  <dc:Bounds x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}"/>\n'
                f'  <bpmndi:BPMNLabel/>\n'
                f'</bpmndi:BPMNShape>'
            )
        for gw in data.get("gateways", []):
            p = positions.get(gw["id"], {"x": 350, "y": 195, "w": 50, "h": 50})
            di_shapes.append(
                f'<bpmndi:BPMNShape id="{gw["id"]}_di" bpmnElement="{gw["id"]}" isMarkerVisible="true">\n'
                f'  <dc:Bounds x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}"/>\n'
                f'  <bpmndi:BPMNLabel/>\n'
                f'</bpmndi:BPMNShape>'
            )
        for ee in data.get("end_events", []):
            p = positions.get(ee["id"], {"x": 500, "y": 200, "w": 36, "h": 36})
            di_shapes.append(
                f'<bpmndi:BPMNShape id="{ee["id"]}_di" bpmnElement="{ee["id"]}">\n'
                f'  <dc:Bounds x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}"/>\n'
                f'  <bpmndi:BPMNLabel/>\n'
                f'</bpmndi:BPMNShape>'
            )

        # DI-Edges generieren – orthogonales Routing (90°-Winkel)
        di_edges = []
        for flow in flows:
            src_p = positions.get(flow["source_ref"])
            tgt_p = positions.get(flow["target_ref"])
            if src_p and tgt_p:
                sx = src_p["x"] + src_p["w"]       # rechte Kante Source
                sy = src_p["y"] + src_p["h"] // 2  # Mitte Source
                tx = tgt_p["x"]                     # linke Kante Target
                ty = tgt_p["y"] + tgt_p["h"] // 2  # Mitte Target
                mx = (sx + tx) // 2                 # horizontaler Mittelpunkt

                if sy == ty:
                    # Gleiche Höhe → direkte horizontale Linie
                    waypoints = [(sx, sy), (tx, ty)]
                else:
                    # Orthogonales L/S-Routing: → runter/hoch → →
                    waypoints = [(sx, sy), (mx, sy), (mx, ty), (tx, ty)]

                wp_xml = "\n  ".join(f'<di:waypoint x="{x}" y="{y}"/>' for x, y in waypoints)
                di_edges.append(
                    f'<bpmndi:BPMNEdge id="{flow["id"]}_di" bpmnElement="{flow["id"]}">\n'
                    f'  {wp_xml}\n'
                    f'</bpmndi:BPMNEdge>'
                )

        process_id = data.get("process_id", "Process_1")
        process_name = data.get("process_name", "Process")
        elements_xml = "\n    ".join(elements)

        # Kein DI – bpmn-auto-layout im Frontend übernimmt das komplette Layout
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"\n'
            '             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
            '             id="Definitions_1"\n'
            '             targetNamespace="http://bpmn.io/schema/bpmn">\n'
            f'  <process id="{process_id}" name="{_esc(process_name)}" isExecutable="true">\n'
            f'    {elements_xml}\n'
            '  </process>\n'
            '</definitions>'
        )

    def validate(self, output: str) -> ValidationResult:
        """XSD-Syntaxvalidierung + pm4py Soundness-Prüfung."""
        timestamp = datetime.now(timezone.utc).isoformat()
        violations: list[Violation] = []

        # Schritt 1: XML-Wohlgeformtheit + XSD-Validierung
        try:
            xml_bytes = output.encode("utf-8")
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            violations.append(Violation(
                error_type=ErrorType.SYNTAX_XSD,
                affected_elements=[],
                description=f"XML nicht wohlgeformt: {e}"
            ))
            return ValidationResult(
                is_valid=False, is_sound=False,
                violations=violations, validation_timestamp=timestamp
            )

        if XSD_PATH.exists():
            xsd_violations = _validate_xsd(root, XSD_PATH)
            violations.extend(xsd_violations)

        # Schritt 2: Referenzintegrität (Metamodell-Constraints)
        ref_violations = _validate_references(root)
        violations.extend(ref_violations)

        is_valid = len(violations) == 0

        # Schritt 3: Soundness via pm4py (nur wenn syntaktisch valide)
        is_sound = False
        if is_valid:
            sound_violations = _validate_soundness(output)
            violations.extend(sound_violations)
            is_sound = len(sound_violations) == 0

        return ValidationResult(
            is_valid=is_valid,
            is_sound=is_sound,
            violations=violations,
            validation_timestamp=timestamp
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen (modul-privat)
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """Escaped XML-Sonderzeichen in Attributwerten."""
    return (text
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _compute_layout(data: dict) -> dict:
    """
    Berechnet einfaches Left-to-Right-Layout für BPMN-Elemente.
    Gibt dict {element_id: {x, y, w, h}} zurück.
    """
    from collections import deque

    TASK_W, TASK_H = 120, 80
    EVENT_W, EVENT_H = 36, 36
    GW_W, GW_H = 50, 50
    H_GAP = 80   # mehr horizontaler Abstand → weniger Überschneidungen beim Routing
    V_GAP = 50
    Y_BASE = 180

    flows = data.get("sequence_flows", [])

    # Element-Typ-Map
    el_type: dict[str, str] = {}
    for e in data.get("start_events", []):
        el_type[e["id"]] = "start"
    for e in data.get("tasks", []):
        el_type[e["id"]] = "task"
    for e in data.get("gateways", []):
        el_type[e["id"]] = "gateway"
    for e in data.get("end_events", []):
        el_type[e["id"]] = "end"

    def dim(eid: str) -> tuple[int, int]:
        t = el_type.get(eid, "task")
        if t in ("start", "end"):
            return EVENT_W, EVENT_H
        if t == "gateway":
            return GW_W, GW_H
        return TASK_W, TASK_H

    # Adjazenzliste aufbauen
    successors: dict[str, list[str]] = {}
    for f in flows:
        successors.setdefault(f["source_ref"], []).append(f["target_ref"])

    # BFS ab StartEvents → Spalten (depths) zuweisen
    depth: dict[str, int] = {}
    starts = [e["id"] for e in data.get("start_events", [])]
    queue: deque = deque()
    for sid in starts:
        depth[sid] = 0
        queue.append(sid)
    while queue:
        node = queue.popleft()
        for tgt in successors.get(node, []):
            if tgt not in depth:
                depth[tgt] = depth[node] + 1
                queue.append(tgt)
    # Elemente ohne Pfad bekommen Spalte nach ihren Vorgängern
    for eid in el_type:
        if eid not in depth:
            depth[eid] = max(depth.values(), default=0) + 1

    # Spalten gruppieren und x-Positionen berechnen
    col_items: dict[int, list[str]] = {}
    for eid, d in depth.items():
        col_items.setdefault(d, []).append(eid)

    col_x: dict[int, int] = {}
    x = 80
    for col in sorted(col_items.keys()):
        col_x[col] = x
        max_w = max(dim(eid)[0] for eid in col_items[col])
        x += max_w + H_GAP

    # y-Positionen: Elemente innerhalb einer Spalte vertikal zentrieren
    positions: dict[str, dict] = {}
    for col, items in col_items.items():
        total_h = sum(dim(eid)[1] for eid in items) + V_GAP * (len(items) - 1)
        y = Y_BASE - total_h // 2
        for eid in items:
            w, h = dim(eid)
            positions[eid] = {"x": col_x[col], "y": y, "w": w, "h": h}
            y += h + V_GAP

    return positions


def _validate_xsd(root: etree._Element, xsd_path: Path) -> list[Violation]:
    violations = []
    try:
        with open(xsd_path, "rb") as f:
            xsd_doc = etree.parse(f)
        schema = etree.XMLSchema(xsd_doc)
        if not schema.validate(root):
            for err in schema.error_log:
                violations.append(Violation(
                    error_type=ErrorType.SYNTAX_XSD,
                    affected_elements=[],
                    description=f"XSD Zeile {err.line}: {err.message}"
                ))
    except Exception as e:
        violations.append(Violation(
            error_type=ErrorType.SYNTAX_XSD,
            affected_elements=[],
            description=f"XSD-Validierung fehlgeschlagen: {e}"
        ))
    return violations


def _validate_references(root: etree._Element) -> list[Violation]:
    """Prüft Referenzintegrität: alle sourceRef/targetRef müssen auf existierende IDs zeigen."""
    violations = []
    ns = {"b": BPMN_NS}

    # Sammle alle definierten IDs
    all_ids = {el.get("id") for el in root.iter() if el.get("id")}

    for flow in root.iter(f"{{{BPMN_NS}}}sequenceFlow"):
        flow_id = flow.get("id", "?")
        for attr in ("sourceRef", "targetRef"):
            ref = flow.get(attr)
            if ref and ref not in all_ids:
                violations.append(Violation(
                    error_type=ErrorType.SYNTAX_METAMODEL,
                    affected_elements=[flow_id],
                    description=f"{attr} '{ref}' verweist auf nicht-existierendes Element"
                ))
    return violations


def _validate_soundness(bpmn_xml: str) -> list[Violation]:
    """
    Semantische Soundness-Prüfung via Petri-Netz-Mapping (DP1: kein LLM).

    Ablauf:
      1. BPMN-XML in temporäre Datei schreiben (pm4py liest aus Datei)
      2. pm4py.read_bpmn() + convert_to_petri_net() → WF-Netz
      3. Woflan-Algorithmus prüft drei Soundness-Eigenschaften:
         - Option to complete: Endzustand von jedem Zustand erreichbar
         - Proper completion: bei Erreichen des Endzustands keine anderen Token
         - Absence of dead transitions: jeder Task auf mindestens einem Pfad

    Woflan ist deterministisch – gleiche Eingabe, gleiches Ergebnis.
    Kein LLM: verhindert Self-Preference Bias (DP1).
    """
    violations = []
    try:
        import tempfile
        import pm4py
        from pm4py.algo.analysis.woflan import algorithm as woflan

        with tempfile.NamedTemporaryFile(suffix=".bpmn", delete=False, mode="w", encoding="utf-8") as f:
            f.write(bpmn_xml)
            tmp_path = f.name

        try:
            bpmn_graph = pm4py.read_bpmn(tmp_path)
            net, im, fm = pm4py.convert_to_petri_net(bpmn_graph)

            # Soundness-Prüfung mit woflan
            is_sound = woflan.apply(net, im, fm, parameters={
                woflan.Parameters.RETURN_ASAP_WHEN_NOT_SOUND: True
            })

            if not is_sound:
                violations.append(Violation(
                    error_type=ErrorType.SEMANTIC_SOUNDNESS,
                    affected_elements=[],
                    description=(
                        "Soundness-Verletzung: Prozess ist nicht sound. "
                        "Mögliche Ursachen: Deadlock, nicht erreichbarer Endzustand, "
                        "oder unkorrekte Terminierung."
                    )
                ))
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        # Soundness-Fehler nicht als hard failure behandeln –
        # manche validen BPMN-Modelle können nicht in Petri-Netze konvertiert werden
        violations.append(Violation(
            error_type=ErrorType.SEMANTIC_SOUNDNESS,
            affected_elements=[],
            description=f"Soundness-Prüfung konnte nicht durchgeführt werden: {e}"
        ))
    return violations

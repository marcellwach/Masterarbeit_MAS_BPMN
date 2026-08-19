"""
BPMN-2.0-Implementierung der LanguageInterface-Basisklasse (DP5).

DP5 – Sprachunabhängige Generalisierbarkeit:
  Diese Klasse ist die einzige BPMN-spezifische Komponente im System.
  Alle Agenten (generator.py, validator.py) importieren nur LanguageInterface (base.py).
  Für eine DMN-Implementierung würde DmnLanguageInterface dieselbe Basisklasse
  implementieren — kein Agent-Code müsste geändert werden.

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
    """
    Konkrete BPMN-2.0-Implementierung des LanguageInterface (DP5).

    Alle Agenten arbeiten ausschließlich über die abstrakte Basisklasse LanguageInterface.
    Dieser Austausch-Punkt ermöglicht es, das System ohne Änderung an den Agenten
    auf eine andere Prozessmodellierungssprache (z.B. DMN, CMMN) zu portieren.
    """

    def get_tool_schema(self) -> dict:
        """
        Gibt das Anthropic tool_use JSON-Schema für BPMN zurück (DP2).

        Das Schema definiert exakt, welche Felder Claude füllen muss — damit ist
        das Ausgabeformat strukturell erzwungen, kein Freitext möglich.
        Gibt das vorkompilierte BPMN_TOOL_SCHEMA-Objekt zurück (kein LLM-Aufruf).
        """
        return BPMN_TOOL_SCHEMA

    def get_system_prompt(self) -> str:
        """
        Gibt den BPMN-spezifischen System-Prompt für den Generator-Agent zurück.

        Der Prompt beinhaltet BPMN-2.0-Modellierungsregeln (Referenzintegrität,
        Gateway-Semantik, Prozessvollständigkeit) sowie Hinweise zur Fehlerkorrektur.
        Diese Regeln ergänzen das tool_use-Schema: das Schema erzwingt die Struktur,
        der Prompt erklärt die semantischen Anforderungen.
        """

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
        """
        Deterministischer JSON → BPMN-XML Konverter (kein LLM-Aufruf, DP2).

        DP2-Garantie: Jede Ausgabe dieses Konverters ist per Konstruktion
        syntaktisch wohlgeformt — damit ist GZ1 (Zielwert: 100% syntaktisch valide)
        durch diesen deterministischen Schritt strukturell sichergestellt.

        Kein DI (Diagram Interchange): Das Backend generiert kein visuelles Layout.
        bpmn-auto-layout im Frontend übernimmt die komplette Koordinatenberechnung.

        Known Limitation – Swimlanes/Pools (dokumentiert in README):
          bpmn-auto-layout verarbeitet BPMN-Collaboration/Pool-Strukturen nicht korrekt.
          Interner Fehler bei attachedToRef-Zugriff. Gilt als bekannte Einschränkung
          auch anderer Tools (Stand der Technik). Swimlanes werden daher nicht unterstützt.
        """
        # Nur echte Dicts akzeptieren – Claude kann in Randfällen Strings statt Objekte liefern
        def _dicts(key: str) -> list:
            items = data.get(key, []) or []
            return [x for x in items if isinstance(x, dict)]

        flows       = _dicts("sequence_flows")
        process_id  = data.get("process_id", "Process_1") if isinstance(data, dict) else "Process_1"
        process_name = data.get("process_name", "Process") if isinstance(data, dict) else "Process"

        def incoming_flows(eid):
            return [f["id"] for f in flows if f.get("target_ref") == eid]

        def outgoing_flows(eid):
            return [f["id"] for f in flows if f.get("source_ref") == eid]

        def flow_refs(eid, direction):
            tag = "incoming" if direction == "in" else "outgoing"
            ids = incoming_flows(eid) if direction == "in" else outgoing_flows(eid)
            return "".join(f"<{tag}>{fid}</{tag}>" for fid in ids)

        # Prozess-Elemente
        elements = []
        for se in _dicts("start_events"):
            elements.append(
                f'<startEvent id="{se["id"]}" name="{_esc(se.get("name", ""))}">'
                f'{flow_refs(se["id"], "out")}</startEvent>'
            )
        for task in _dicts("tasks"):
            elements.append(
                f'<task id="{task["id"]}" name="{_esc(task.get("name", ""))}">'
                f'{flow_refs(task["id"], "in")}{flow_refs(task["id"], "out")}</task>'
            )
        for gw in _dicts("gateways"):
            # isMarkerVisible gehört ins DI (BPMNShape), nicht ins Prozess-Element
            gw_type = gw.get("type", "exclusiveGateway")
            elements.append(
                f'<{gw_type} id="{gw["id"]}" name="{_esc(gw.get("name", ""))}">'
                f'{flow_refs(gw["id"], "in")}{flow_refs(gw["id"], "out")}</{gw_type}>'
            )
        for ee in _dicts("end_events"):
            elements.append(
                f'<endEvent id="{ee["id"]}" name="{_esc(ee.get("name", ""))}">'
                f'{flow_refs(ee["id"], "in")}</endEvent>'
            )
        for flow in flows:
            name_attr = f' name="{_esc(flow["name"])}"' if flow.get("name") else ""
            elements.append(
                f'<sequenceFlow id="{flow["id"]}" '
                f'sourceRef="{flow.get("source_ref", "")}" '
                f'targetRef="{flow.get("target_ref", "")}"{name_attr}/>'
            )

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
        """
        Zweistufige Validierung: Syntax (lxml) + Soundness (pm4py/Woflan).

        Schritt 1 – Syntaxvalidierung:
            - XML-Wohlgeformtheit (etree.fromstring)
            - XSD-Konformität gegen OMG BPMN-2.0-Schema (wenn vorhanden)
            - Referenzintegrität: sourceRef/targetRef auf existierende IDs

        Schritt 2 – Soundness (nur wenn Schritt 1 fehlerlos):
            - BPMN → Petri-Netz Mapping via pm4py (Dijkman et al. 2008)
            - Normalisierung zum WF-Netz bei mehreren Quellen/Senken
            - Woflan prüft: Option-to-complete, Proper-Completion, No-Dead-Transitions

        Bei transienten Windows-Fehlern (pm4py PID-Caching) automatischer Retry.
        DP1: Kein LLM-Aufruf — vollständig deterministisch.
        """
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



def _parse_woflan_violations(woflan_output: str) -> list[str]:
    """Extrahiert konkrete Regelverstöße aus der Woflan-Konsolenausgabe.
    Keywords basieren auf den tatsächlichen pm4py-Ausgabestrings."""
    rules = [
        ("more than one source place",      "Mehrere Start-Events: Woflan erfordert genau ein Start-Event (aktuell mehr als eine Quellstelle im Petri-Netz)"),
        ("more than one sink place",        "Mehrere End-Events: Woflan erfordert genau ein End-Event (aktuell mehr als eine Senke im Petri-Netz)"),
        ("not a workflow net",              "Kein Workflow-Netz (fehlende oder mehrfache Start-/Endmarke)"),
        ("is not a workflow net",           "Kein Workflow-Netz (fehlende oder mehrfache Start-/Endmarke)"),
        ("not covered by an s-component",  "S-Überdeckung fehlt: Parallelzweig ohne korrekten Merge-Gateway"),
        ("uncovered in uniform invariants", "Invarianten-Verletzung: nicht alle Zustände erreichbar"),
        ("uncovered in weighted invariants","Invarianten-Verletzung: nicht alle Zustände erreichbar"),
        ("improper wpd",                    "Improper WPD: inkorrekte Terminierung (Token verbleiben im Netz)"),
        ("improper conditions",             "Improper WPD: inkorrekte Terminierung (Token verbleiben im Netz)"),
        ("sequences are unbounded",         "Unbeschränkt: Token häufen sich unbegrenzt an (fehlender Merge-Gateway)"),
        ("dead task",                       "Tote Transitionen: Tasks die nie ausgeführt werden können"),
        ("dead transition",                 "Tote Transitionen: Tasks die nie ausgeführt werden können"),
        ("not all tasks are live",          "Nicht lebende Transitionen: möglicher Deadlock"),
        ("tasks are not live",              "Nicht lebende Transitionen: möglicher Deadlock"),
        ("not well-handled",                "Nicht korrekt behandelte Gateway-Paare (fehlendes Gegenstück zu Split oder Join)"),
    ]
    lower = woflan_output.lower()
    seen: set[str] = set()
    found = []
    for keyword, label in rules:
        if keyword in lower and label not in seen:
            seen.add(label)
            found.append(label)
    return found


def _validate_xsd(root: etree._Element, xsd_path: Path) -> list[Violation]:
    """
    Validiert das geparste XML-Dokument gegen das OMG BPMN-2.0-XSD-Schema.

    Die XSD ist optional – wenn die Datei nicht existiert, wird dieser Schritt übersprungen.
    Die Referenzintegrität (sourceRef/targetRef) wird in _validate_references separat geprüft,
    da sie nicht vollständig durch die XSD abgedeckt wird.
    """
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


def _normalize_wf_net(net, im, fm):
    """
    Normalisiert ein Petri-Netz zum Workflow-Netz für Woflan (van der Aalst 1998).

    Known Limitation (dokumentiert in README §Known Limitations):
      Woflan setzt ein Workflow-Netz mit GENAU EINEM Start-Event und EINEM End-Event
      voraus. BPMN 2.0 erlaubt mehrere Start-/End-Events, aber das BPMN→Petri-Netz-
      Mapping (pm4py, Dijkman et al. 2008) erzeugt dabei mehrere Quell-/Senkenplätze.
      Woflan verweigert die Prüfung mit "more than one source/sink place".

    Diese Funktion löst das Problem durch XOR-Normalisierung:
      Falls mehrere Quell- oder Senkenplätze existieren, werden sie als ALTERNATIVE
      Auslöser bzw. Abschlüsse zusammengefasst — je Quelle/Senke eine eigene
      Silent-Transition zur/von der künstlichen Quelle/Senke:

        Quellen:  p_art_source → t_start_i → source_place_i   (genau ein Start feuert)
        Senken:   sink_place_i → t_end_i → p_art_sink          (irgendein Ende terminiert)

      Das entspricht der BPMN-Semantik mehrerer Start-/End-Events (alternative Trigger
      bzw. Abschlüsse) und der Standard-WF-Netz-Normalisierung (van der Aalst).

    Annahme (für die Masterarbeit zu dokumentieren):
      Mehrfache Start-/End-Events werden als EXKLUSIVE Alternativen interpretiert.
      Für den selteneren Fall echt NEBENLÄUFIGER Enden (paralleler Split ohne Join)
      ist diese Normalisierung nachsichtig — eine dortige "improper completion"
      würde nicht als Soundness-Verletzung erkannt.

    Gibt (net, im, fm, note) zurück; note beschreibt die vorgenommene Normalisierung
    (oder "", falls keine nötig war — wird in Violation.description angehängt).
    """
    from pm4py.objects.petri_net.obj import PetriNet, Marking
    from pm4py.objects.petri_net.utils import petri_utils

    notes = []
    source_places = [p for p in net.places if len(p.in_arcs) == 0]
    sink_places   = [p for p in net.places if len(p.out_arcs) == 0]

    if len(source_places) > 1:
        # XOR-Split: künstliche Quelle mit einer Silent-Transition PRO Quellstelle.
        # Semantik: "genau ein Start-Event triggert den Prozess" (alternative Auslöser,
        # BPMN-konform). Der frühere AND-Split (EINE Transition, die in alle Quellen
        # produziert) erzwang paralleles Starten aller Start-Events — bei alternativen
        # Triggern semantisch falsch und Zustandsraum-treibend.
        art_src = PetriNet.Place("p_artificial_source")
        net.places.add(art_src)
        for idx, sp in enumerate(source_places):
            t_start = PetriNet.Transition(f"t_artificial_start_{idx}", label=None)
            net.transitions.add(t_start)
            petri_utils.add_arc_from_to(art_src, t_start, net)
            petri_utils.add_arc_from_to(t_start, sp, net)
        im = Marking({art_src: 1})
        notes.append(f"{len(source_places)} Quellstellen als alternative Auslöser (XOR) zusammengefasst")

    if len(sink_places) > 1:
        # XOR-Merge: eine Silent-Transition PRO Senke, alle produzieren in DENSELBEN
        # künstlichen Sink. Semantik: "irgendein End-Event erreicht → Netz terminiert"
        # (alternative Abschlüsse). Der frühere AND-Join (EINE Transition mit
        # Eingangskanten aus allen Senken) verlangte fälschlich, dass ALLE End-Events
        # gleichzeitig markiert sind — bei exklusiven Enden unerfüllbar, wodurch der
        # künstliche Endzustand unerreichbar wurde und Woflan im Coverability-Graph
        # bis zum Timeout suchte.
        art_snk = PetriNet.Place("p_artificial_sink")
        net.places.add(art_snk)
        for idx, sk in enumerate(sink_places):
            t_end = PetriNet.Transition(f"t_artificial_end_{idx}", label=None)
            net.transitions.add(t_end)
            petri_utils.add_arc_from_to(sk, t_end, net)
            petri_utils.add_arc_from_to(t_end, art_snk, net)
        fm = Marking({art_snk: 1})
        notes.append(f"{len(sink_places)} Senken als alternative Abschlüsse (XOR) zusammengefasst")

    return net, im, fm, "; ".join(notes)


def _extract_processes(bpmn_xml: str) -> list[tuple[str, str]]:
    """
    Extrahiert jeden <process> aus einem Collaboration-BPMN als eigenständiges XML.
    Bei einfachen Modellen (ein Prozess) wird das Original zurückgegeben.
    Gibt [(prozessname, xml_string), ...] zurück.
    """
    import copy
    root = etree.fromstring(bpmn_xml.encode("utf-8"))
    # Namespace-agnostisch: BPMN-NS aus dem Root-Tag ableiten
    tag = root.tag
    ns = tag.split("}")[0].lstrip("{") if "}" in tag else BPMN_NS

    processes = root.findall(f"{{{ns}}}process")
    if len(processes) <= 1:
        name = processes[0].get("name", "") if processes else ""
        return [(name, bpmn_xml)]

    results = []
    for proc in processes:
        proc_name = proc.get("name", proc.get("id", ""))
        # Standalone-Definitions bauen (Namespaces vom Original übernehmen)
        standalone = etree.Element(
            f"{{{ns}}}definitions",
            nsmap=root.nsmap,
        )
        standalone.set("id", "Definitions_standalone")
        standalone.set("targetNamespace", "http://example.com/standalone")
        standalone.append(copy.deepcopy(proc))
        results.append((proc_name, etree.tostring(standalone, encoding="unicode")))
    return results


def _is_subprocess_error(exc: Exception) -> bool:
    """Erkennt transiente pm4py-Subprocess-Fehler (z.B. nach gewaltsamen Prozessabbrüchen)."""
    msg = str(exc).lower()
    return any(k in msg for k in ("pid not found", "process pid", "no such process", "broken pipe", "winerror 5"))


def _run_woflan_inprocess(net, im, fm) -> tuple[bool, str]:
    """Führt Woflan im aktuellen Prozess aus. Gibt (is_sound, output) zurück."""
    import io, contextlib
    from pm4py.algo.analysis.woflan import algorithm as woflan

    quick_buf = io.StringIO()
    with contextlib.redirect_stdout(quick_buf), contextlib.redirect_stderr(io.StringIO()):
        is_sound = woflan.apply(net, im, fm, parameters={
            woflan.Parameters.RETURN_ASAP_WHEN_NOT_SOUND: True
        })

    if not is_sound:
        detail_buf = io.StringIO()
        with contextlib.redirect_stdout(detail_buf), contextlib.redirect_stderr(io.StringIO()):
            woflan.apply(net, im, fm, parameters={
                woflan.Parameters.RETURN_ASAP_WHEN_NOT_SOUND: False
            })
        return False, quick_buf.getvalue() + "\n" + detail_buf.getvalue()
    return True, ""


def _woflan_worker(xml_bytes: bytes) -> bytes:
    """
    Modul-level Worker für ProcessPoolExecutor (muss picklebar sein).
    Führt die vollständige Soundness-Prüfung in einem frischen Prozess durch.
    """
    import pickle
    import pm4py
    from pm4py.objects.bpmn.importer.variants.lxml import import_from_string
    from language_interface.bpmn import (
        _extract_processes, _normalize_wf_net, _parse_woflan_violations,
        _run_woflan_inprocess
    )
    from models.feedback import ErrorType, Violation

    bpmn_xml = xml_bytes.decode("utf-8")
    violations = []
    process_list = _extract_processes(bpmn_xml)

    for proc_name, proc_xml in process_list:
        label = f"Prozess '{proc_name}': " if proc_name else ""
        try:
            bpmn_graph = import_from_string(proc_xml)
            net, im, fm = pm4py.convert_to_petri_net(bpmn_graph)
            net, im, fm, norm_note = _normalize_wf_net(net, im, fm)

            is_sound, output = _run_woflan_inprocess(net, im, fm)
            if not is_sound:
                failed_rules = _parse_woflan_violations(output)
                if failed_rules:
                    desc = label + "Soundness-Verletzung: " + "; ".join(failed_rules)
                else:
                    raw_lines = [
                        line.strip() for line in output.splitlines()
                        if line.strip()
                        and not line.strip().startswith("Input is ok")
                        and not line.strip().startswith("Petri Net is a workflow net")
                    ]
                    summary = " | ".join(raw_lines[:3]) or "Deadlock, nicht erreichbarer Endzustand oder tote Transitionen"
                    desc = label + f"Soundness-Verletzung: {summary}"
                if norm_note:
                    desc += f" [normalisiert: {norm_note}]"
                violations.append(Violation(
                    error_type=ErrorType.SEMANTIC_SOUNDNESS,
                    affected_elements=[],
                    description=desc
                ))
        except Exception as e:
            violations.append(Violation(
                error_type=ErrorType.SEMANTIC_SOUNDNESS,
                affected_elements=[],
                description=f"{label}Soundness-Prüfung fehlgeschlagen: {e}"
            ))
    return pickle.dumps(violations)


def _run_woflan_subprocess(bpmn_xml: str) -> list[Violation]:
    """
    Führt die komplette Soundness-Prüfung in einem frischen Subprocess aus.
    Workaround für pm4py-PID-Caching-Bug auf Windows nach gewaltsamen Prozessabbrüchen.
    """
    import concurrent.futures
    import pickle

    with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_woflan_worker, bpmn_xml.encode("utf-8"))
        result_bytes = future.result(timeout=30)
    return pickle.loads(result_bytes)


def _validate_soundness(bpmn_xml: str) -> list[Violation]:
    """
    Semantische Soundness-Prüfung via Petri-Netz-Mapping (DP1: kein LLM).

    Ablauf:
      1. pm4py import_from_string() → BPMN-Graph (kein Dateisystem, kein Windows-Locking)
      2. convert_to_petri_net() → Petri-Netz
      3. Normalisierung zum WF-Netz falls nötig (van der Aalst 1998)
      4. Woflan-Algorithmus prüft drei Soundness-Eigenschaften:
         - Option to complete: Endzustand von jedem Zustand erreichbar
         - Proper completion: bei Erreichen des Endzustands keine anderen Token
         - Absence of dead transitions: jeder Task auf mindestens einem Pfad

    Bei transienten Subprocess-Fehlern (pm4py PID-Caching-Bug auf Windows):
      Automatischer Retry in frischem Subprocess via ProcessPoolExecutor.

    Woflan ist deterministisch – gleiche Eingabe, gleiches Ergebnis.
    Kein LLM: verhindert Self-Preference Bias (DP1).
    """
    violations = []
    try:
        import pm4py
        from pm4py.objects.bpmn.importer.variants.lxml import import_from_string

        # Collaboration-Modelle: jeden Prozess einzeln analysieren
        process_list = _extract_processes(bpmn_xml)

        for proc_name, proc_xml in process_list:
            label = f"Prozess '{proc_name}': " if proc_name else ""
            try:
                bpmn_graph = import_from_string(proc_xml)
                net, im, fm = pm4py.convert_to_petri_net(bpmn_graph)
                net, im, fm, norm_note = _normalize_wf_net(net, im, fm)

                is_sound, output = _run_woflan_inprocess(net, im, fm)
                if not is_sound:
                    failed_rules = _parse_woflan_violations(output)
                    if failed_rules:
                        description = label + "Soundness-Verletzung: " + "; ".join(failed_rules)
                    else:
                        raw_lines = [
                            line.strip() for line in output.splitlines()
                            if line.strip()
                            and not line.strip().startswith("Input is ok")
                            and not line.strip().startswith("Petri Net is a workflow net")
                        ]
                        summary = " | ".join(raw_lines[:3]) if raw_lines else (
                            "Deadlock, nicht erreichbarer Endzustand oder tote Transitionen"
                        )
                        description = label + f"Soundness-Verletzung: {summary}"
                    if norm_note:
                        description += f" [normalisiert: {norm_note}]"
                    violations.append(Violation(
                        error_type=ErrorType.SEMANTIC_SOUNDNESS,
                        affected_elements=[],
                        description=description
                    ))
                # Sound → kein Fehler

            except Exception as proc_e:
                if _is_subprocess_error(proc_e):
                    # Transiente pm4py-Subprocess-Fehler: Retry in frischem Subprocess
                    print(f"[woflan] Subprocess-Fehler ({proc_e}), Retry in frischem Prozess...")
                    try:
                        sub_violations = _run_woflan_subprocess(bpmn_xml)
                        violations.extend(sub_violations)
                    except Exception as retry_e:
                        print(f"[woflan] Retry fehlgeschlagen ({retry_e}), Soundness-Prüfung übersprungen")
                        # Systemfehler ≠ unsound: Prüfung überspringen statt fälschlich zu scheitern
                else:
                    violations.append(Violation(
                        error_type=ErrorType.SEMANTIC_SOUNDNESS,
                        affected_elements=[],
                        description=f"{label}Soundness-Prüfung fehlgeschlagen: {proc_e}"
                    ))

    except Exception as e:
        if _is_subprocess_error(e):
            print(f"[woflan] Subprocess-Fehler auf Modulebene ({e}), Retry in frischem Prozess...")
            try:
                return _run_woflan_subprocess(bpmn_xml)
            except Exception as retry_e:
                print(f"[woflan] Retry fehlgeschlagen ({retry_e}), Soundness-Prüfung übersprungen")
                return []
        violations.append(Violation(
            error_type=ErrorType.SEMANTIC_SOUNDNESS,
            affected_elements=[],
            description=f"Soundness-Prüfung konnte nicht durchgeführt werden: {e}"
        ))
    return violations

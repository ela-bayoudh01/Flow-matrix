"""Génère la fiche PDF d'une inversion d'action décidée sur un Flow (2026-09-03, demande de
l'encadrant) -- même structure que la fiche texte de l'ACL Engine (zone/IP/port/protocole/
action, `Services/acl_engine.py::_format_create_rule_text`), mais déclenchée directement par
la décision de bloquer/autoriser un flux, pas par une génération scopée à un cycle.

Générée à la demande depuis une ligne `FlowValidationHistory` précise (jamais depuis l'état
courant du `Flow`, qui continue d'évoluer après coup) -- la fiche reste fidèle à ce qui a
réellement été décidé à cet instant, même si le Flow a été retouché depuis. `fpdf2` : pur
Python, zéro dépendance système (contrairement à weasyprint/Cairo), cohérent avec le principe
du projet "logique métier dans le backend" (pas une librairie JS côté frontend).
"""

from typing import Optional

from fpdf import FPDF

from .models import Flow, FlowValidationHistory, NetworkPolicy, RuleEnforcementClaim, ValidationCycle

TITLE = "Fiche de changement d'action - Nouvelair Flow Matrix"
CYCLE_REPORT_TITLE = "Rapport de cloture de cycle - Nouvelair Flow Matrix"
RULE_NOT_ENFORCED_TITLE = "Fiche de non-application de regle - Nouvelair Flow Matrix"
NETWORK_POLICY_TITLE = "Fiche de politique de sous-reseau - Nouvelair Flow Matrix"

# Même mapping que flow_validation.py::STATUS_FOR_ACTION (inversé) -- jamais une deuxième
# correspondance Allow/Block susceptible de diverger.
_ACTION_LABEL = {"Allow": "Autorise", "Block": "Bloque"}


def _narrative_sentence(src_ip: str, dst_ip: str, dst_port: Optional[int], action: Optional[str]) -> str:
    """Phrase structurée générée SYSTÉMATIQUEMENT à partir des champs déjà connus (src/dst/
    port/action) -- demande de l'encadrant (2026-09-10) : jamais dépendante du texte libre de
    justification pour dire CE QUI a été décidé, toujours en tête de la fiche (ou de chaque
    décision, pour le rapport de cycle qui en regroupe plusieurs). Le champ justification
    reste en complément -- POURQUOI -- jamais la source de cette phrase.
    """
    port = str(dst_port) if dst_port is not None else "tout port"
    verb = _ACTION_LABEL.get(action, action or "(action non renseignee)")
    return f"Le trafic de {src_ip} vers {dst_ip} sera {verb} sur le port {port}."


def _network_policy_narrative_sentence(src_cidr: str, destination: str, dst_port: Optional[int], action: Optional[str]) -> str:
    """Même mécanisme que _narrative_sentence ci-dessus (même _ACTION_LABEL, même principe
    "toujours en tête, jamais dépendante du texte libre") -- formulation adaptée à une
    politique de SOUS-RÉSEAU (pas un Flow précis) : "Tout le trafic depuis [CIDR]...", demande
    explicite de l'encadrant (2026-09-10)."""
    port = str(dst_port) if dst_port is not None else "tout port"
    verb = _ACTION_LABEL.get(action, action or "(action non renseignee)")
    return f"Tout le trafic depuis {src_cidr} vers {destination} sera {verb} sur le port {port}."


def build_action_change_pdf(history: FlowValidationHistory, flow: Flow) -> bytes:
    pdf = FPDF()
    pdf.set_title(TITLE)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, TITLE)
    pdf.ln(2)

    # Phrase structurée, toujours en tête (2026-09-10) -- jamais dépendante du texte libre de
    # justification pour dire CE QUI a été décidé.
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 6, _narrative_sentence(flow.src_ip, flow.dst_ip, flow.dst_port, history.decided_action))
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 5, "Proposition manuelle -- a verifier et appliquer par l'equipe reseau dans FMC. Aucune modification n'a ete appliquee automatiquement sur le firewall.")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    rows = [
        ("Source (IP)", flow.src_ip),
        ("Destination (IP)", flow.dst_ip),
        ("Port destination", str(flow.dst_port) if flow.dst_port is not None else "any"),
        ("Protocole", (flow.protocol or "any").upper()),
        ("Application", flow.web_application or flow.application_protocol or "(non renseignee)"),
        ("Zone source", flow.ingress_zone or "(non renseignee)"),
        ("Zone destination", flow.egress_zone or "(non renseignee)"),
        ("Source (site/ACPolicy)", flow.source or "(non renseignee)"),
        ("", ""),
        ("Action avant", history.observed_action_before or "(non renseignee)"),
        ("Action decidee", history.decided_action or "(non renseignee)"),
        ("", ""),
        ("Decide par", history.validated_by or "(non renseigne)"),
        ("Date de la decision", history.created_at.strftime("%Y-%m-%d %H:%M:%S")),
    ]
    _add_table(pdf, rows)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Justification", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, history.justification or "(aucune)")

    return bytes(pdf.output())


def _add_table(pdf: FPDF, rows: list[tuple[str, str]]) -> None:
    label_width = 55
    for label, value in rows:
        if not label and not value:
            pdf.ln(3)
            continue
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_width, 7, label, border=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def build_rule_not_enforced_pdf(claim: RuleEnforcementClaim, flow: Flow, history: Optional[FlowValidationHistory]) -> bytes:
    """Fiche de "réclamation" (2026-09-10, demande de l'encadrant) -- texte volontairement
    différent de la fiche de changement (build_action_change_pdf ci-dessus) : celle-ci ne
    décide rien, elle CONSTATE qu'une décision déjà prise (identifiée via `history`, la même
    ligne FlowValidationHistory qui a posé `flow.decided_action`) n'est toujours pas appliquée
    dans FMC, et inclut le suivi léger (`claim`) -- première détection, dernière réclamation,
    nombre de fois réclamé.
    """
    pdf = FPDF()
    pdf.set_title(RULE_NOT_ENFORCED_TITLE)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, RULE_NOT_ENFORCED_TITLE)
    pdf.ln(2)

    # Phrase structurée, toujours en tête (2026-09-10) -- l'action DÉCIDÉE (attendue), pas
    # celle réellement observée (justement le problème que cette fiche signale).
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 6, _narrative_sentence(flow.src_ip, flow.dst_ip, flow.dst_port, flow.decided_action))
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    decision_date = history.created_at.strftime("%Y-%m-%d") if history else "date inconnue"
    pdf.multi_cell(
        0, 5,
        f"Relance -- la regle decidee le {decision_date} n'est TOUJOURS PAS appliquee dans FMC, "
        "a ce jour. A verifier et appliquer par l'equipe reseau. Aucune modification n'a ete "
        "appliquee automatiquement sur le firewall.",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    rows = [
        ("Source (IP)", flow.src_ip),
        ("Destination (IP)", flow.dst_ip),
        ("Port destination", str(flow.dst_port) if flow.dst_port is not None else "any"),
        ("Protocole", (flow.protocol or "any").upper()),
        ("Application", flow.web_application or flow.application_protocol or "(non renseignee)"),
        ("Source (site/ACPolicy)", flow.source or "(non renseignee)"),
        ("", ""),
        ("Action decidee (attendue)", flow.decided_action or "(non renseignee)"),
        ("Action observee (ce cycle)", flow.cycle_dominant_action or "(non renseignee)"),
        ("", ""),
        ("Decide par", (history.validated_by if history else None) or "(non renseigne)"),
        ("Date de la decision", history.created_at.strftime("%Y-%m-%d %H:%M:%S") if history else "(non renseignee)"),
        ("", ""),
        ("Premiere detection de l'ecart", claim.first_detected_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("Derniere reclamation", claim.last_claimed_at.strftime("%Y-%m-%d %H:%M:%S") if claim.last_claimed_at else "(premiere reclamation)"),
        ("Nombre de reclamations", str(claim.claim_count)),
    ]
    _add_table(pdf, rows)

    if history and history.justification:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Justification de la decision d'origine", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, history.justification)

    return bytes(pdf.output())


def build_cycle_report_pdf(cycle: ValidationCycle, rows: list[tuple[FlowValidationHistory, Flow]]) -> bytes:
    """Rapport de clôture de cycle (2026-09-10, demande de l'encadrant) -- une ligne par
    décision "Changer la règle" prise durant `cycle` (voir Services/validation_cycle_engine.py
    ::build_cycle_report pour le calcul de `rows`, jamais recalculé ici), même contenu que la
    fiche individuelle (build_action_change_pdf) mais groupé en un seul document.
    """
    pdf = FPDF()
    pdf.set_title(CYCLE_REPORT_TITLE)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, CYCLE_REPORT_TITLE)
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    closed_by = f" par {cycle.closed_by}" if cycle.closed_by else ""
    pdf.multi_cell(
        0, 5,
        f"{cycle.source} -- cloture le {cycle.closed_at.strftime('%Y-%m-%d %H:%M:%S')}{closed_by}. "
        "Proposition manuelle -- a verifier et appliquer par l'equipe reseau dans FMC.",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if not rows:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, 'Aucun changement de regle ("Changer la regle") decide durant ce cycle.')
        return bytes(pdf.output())

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"{len(rows)} changement(s) de regle decide(s) durant ce cycle", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 9)
    with pdf.table(text_align="LEFT") as table:
        header = table.row()
        for label in ("Source", "Destination", "Port", "Application", "Decidee", "Decide par", "Date"):
            header.cell(label)
        for history, flow in rows:
            row = table.row()
            row.cell(flow.src_ip)
            row.cell(flow.dst_ip)
            row.cell(str(flow.dst_port) if flow.dst_port is not None else "any")
            row.cell(flow.web_application or flow.application_protocol or "-")
            row.cell(history.decided_action or "-")
            row.cell(history.validated_by or "-")
            row.cell(history.created_at.strftime("%Y-%m-%d"))

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Detail par decision", new_x="LMARGIN", new_y="NEXT")
    for history, flow in rows:
        # new_x="LMARGIN", new_y="NEXT" explicites -- contrairement à cell(), multi_cell() ne
        # remet PAS x à la marge gauche par défaut (laisse le curseur juste après le dernier
        # caractère rendu) : sans ça, le multi_cell() suivant hérite d'une largeur quasi
        # nulle et fpdf2 lève "Not enough horizontal space to render a single character" --
        # bug réel trouvé en testant (jamais rencontré avant : chaque autre multi_cell de ce
        # fichier est soit unique, soit suivi d'un ln()/cell() qui remet x, jamais deux
        # multi_cell() consécutifs comme dans cette boucle).
        #
        # Phrase structurée EN TÊTE de chaque décision (2026-09-10) -- remplace l'ancien
        # "src -> dst:port" brut : dit directement CE QUI a été décidé, jamais dépendante du
        # texte libre de justification qui suit, affiché en complément (POURQUOI).
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(
            0, 5, _narrative_sentence(flow.src_ip, flow.dst_ip, flow.dst_port, history.decided_action),
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, history.justification or "(aucune)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    return bytes(pdf.output())


def build_network_policy_pdf(policy: NetworkPolicy) -> bytes:
    """Fiche d'une politique de sous-réseau (2026-09-10, demande de l'encadrant) -- même style
    que les autres fiches (titre, phrase structurée en tête, tableau, justification en
    complément), mais SANS AUCUN lien avec un Flow/FlowValidationHistory précis : NetworkPolicy
    porte tous ses propres champs, rien à aller chercher ailleurs.
    """
    pdf = FPDF()
    pdf.set_title(NETWORK_POLICY_TITLE)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, NETWORK_POLICY_TITLE)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(
        0, 6,
        _network_policy_narrative_sentence(policy.src_cidr, policy.destination, policy.dst_port, policy.action),
    )
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0, 5,
        "Politique de sous-reseau -- suggestion basee sur un regroupement d'IP observees dans "
        "les logs, PAS le decoupage reseau reel de Nouvelair. Proposition manuelle -- a "
        "verifier et appliquer par l'equipe reseau dans FMC si pertinent. Aucune modification "
        "n'a ete appliquee automatiquement sur le firewall.",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    rows = [
        ("CIDR source", policy.src_cidr),
        ("Destination", policy.destination),
        ("Port destination", str(policy.dst_port) if policy.dst_port is not None else "any"),
        ("Protocole", (policy.protocol or "any").upper()),
        ("Source (site/ACPolicy)", policy.source or "(non renseignee)"),
        ("", ""),
        ("Action", policy.action),
        ("", ""),
        ("Decide par", policy.decided_by or "(non renseigne)"),
        ("Date", policy.created_at.strftime("%Y-%m-%d %H:%M:%S")),
    ]
    _add_table(pdf, rows)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Justification", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, policy.justification)

    return bytes(pdf.output())

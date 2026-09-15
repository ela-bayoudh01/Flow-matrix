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

import re
from pathlib import Path
from typing import Optional

from fpdf import FPDF
from fpdf.image_parsing import preload_image

from .models import Flow, FlowValidationHistory, NetworkPolicy, RuleEnforcementClaim, ValidationCycle
from .time_utils import utcnow

TITLE = "Fiche de changement d'action - Nouvelair Flow Matrix"
CYCLE_REPORT_TITLE = "Rapport de cloture de cycle - Nouvelair Flow Matrix"
RULE_NOT_ENFORCED_TITLE = "Fiche de non-application de regle - Nouvelair Flow Matrix"
NETWORK_POLICY_TITLE = "Fiche de politique de sous-reseau - Nouvelair Flow Matrix"
TECHNICAL_GUIDE_TITLE = "Guide technique - Nouvelair Flow Matrix"

# Emplacement des logos (2026-09-13, demande de l'encadrant -- gabarit commun) : dépose le
# fichier définitif ICI, sous ce nom exact -- aucune modification de code requise. Résolus via
# Path(__file__) (pas un chemin relatif au répertoire de lancement, fragile selon d'où
# `uvicorn` est démarré). Absent -> l'en-tête l'ignore silencieusement (cf. NouvelairPDF.header
# ci-dessous), jamais un fichier PDF cassé pour un logo manquant.
_LOGO_PATH = Path(__file__).parent / "assets" / "logo_Nouvelair.png"
_FLOW_GUARD_LOGO_PATH = Path(__file__).parent / "assets" / "Logo+Name.png"

# Hauteur commune des deux logos d'en-tête -- même valeur des deux côtés pour rester alignés
# visuellement malgré des largeurs différentes (cf. header() ci-dessous, qui calcule la largeur
# réelle de chaque logo à cette hauteur avant de le positionner).
_HEADER_LOGO_HEIGHT = 12


class NouvelairPDF(FPDF):
    """Gabarit commun à toutes les fiches PDF du projet (2026-09-13, demande de l'encadrant) --
    en-tête (logo Nouvelair à gauche, logo "Flow Guard" à droite, ligne de séparation) et pied
    de page (numéro de page, date de génération, mention "Document interne") appliqués aux 4
    générateurs existants (build_action_change_pdf, build_rule_not_enforced_pdf,
    build_cycle_report_pdf, build_network_policy_pdf) -- une seule définition, jamais 4 mises
    en page indépendantes susceptibles de diverger.

    header()/footer() : rappelées AUTOMATIQUEMENT par fpdf2 à chaque add_page(), y compris
    les pages ajoutées automatiquement en cours de rendu quand le contenu déborde (le rapport
    de clôture de cycle, par exemple, peut s'étaler sur plusieurs pages selon le nombre de
    décisions) -- seule façon correcte de garantir l'en-tête/pied sur un document multi-pages.
    De simples fonctions build_pdf_header(pdf)/build_pdf_footer(pdf) appelées une fois après
    add_page()/avant output() rateraient toute page ajoutée après coup par ce mécanisme.
    """

    def header(self) -> None:
        if _LOGO_PATH.exists():
            self.image(str(_LOGO_PATH), x=10, y=8, h=_HEADER_LOGO_HEIGHT)

        if _FLOW_GUARD_LOGO_PATH.exists():
            # Largeur réelle à _HEADER_LOGO_HEIGHT calculée depuis les dimensions PIXEL du
            # fichier (preload_image, jamais Pillow -- pas une dépendance du projet) : les deux
            # logos ne font pas forcément la même largeur, contrairement à un texte dont la
            # largeur se connaît à l'avance -- collé au bord droit (self.w - 10) quel que soit
            # son ratio, jamais une largeur supposée/codée en dur qui casserait si le fichier
            # est remplacé par un logo de forme différente.
            _, _, info = preload_image(self.image_cache, str(_FLOW_GUARD_LOGO_PATH))
            logo_width = _HEADER_LOGO_HEIGHT * info["w"] / info["h"]
            self.image(str(_FLOW_GUARD_LOGO_PATH), x=self.w - 10 - logo_width, y=8, h=_HEADER_LOGO_HEIGHT)

        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(10, 24, self.w - 10, 24)

        self.set_y(28)
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.2)
        self.line(10, self.get_y(), self.w - 10, self.get_y())
        self.ln(2)

        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        generated_at = utcnow().strftime("%Y-%m-%d %H:%M")
        # "{nb}" : alias substitué par fpdf2 au nombre total de pages à la génération finale
        # (alias_nb_pages, actif par défaut) -- jamais recalculé à la main.
        self.cell(0, 6, f"Document interne -- Nouvelair | Genere le {generated_at} | Page {self.page_no()}/{{nb}}", align="C")
        self.set_text_color(0, 0, 0)


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
    pdf = NouvelairPDF()
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
    pdf = NouvelairPDF()
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


def build_cycle_report_pdf(
    cycle: ValidationCycle,
    rows: list[tuple[FlowValidationHistory, Flow]],
    policies: list[NetworkPolicy],
) -> bytes:
    """Rapport de clôture de cycle (2026-09-10, demande de l'encadrant) -- une ligne par
    décision "Changer la règle" prise durant `cycle` (voir Services/validation_cycle_engine.py
    ::build_cycle_report pour le calcul de `rows`, jamais recalculé ici), même contenu que la
    fiche individuelle (build_action_change_pdf) mais groupé en un seul document.

    `policies` (2026-09-14, demande de l'encadrant) : les `NetworkPolicy` décidées durant ce
    même cycle (Services/validation_cycle_engine.py::build_cycle_network_policies_report,
    même fenêtrage que `rows`) -- affichées dans une section séparée après les changements de
    flux, jamais mélangées à `rows` : une politique de sous-réseau n'a pas de Flow associé.
    """
    pdf = NouvelairPDF()
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

    # Section "changements de flux" -- son placeholder ("Aucun changement...") reste affiché
    # même si `rows` est vide, contrairement à la section politiques de sous-réseau plus bas
    # (masquée entièrement si vide, cf. docstring) : comportement pré-existant, conservé tel
    # quel, on ne fait plus un `return` anticipé pour laisser la place à la section suivante.
    if not rows:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, 'Aucun changement de regle ("Changer la regle") decide durant ce cycle.')
    else:
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

    # Section "politiques de sous-réseau" (2026-09-14, demande de l'encadrant) -- décisions
    # NetworkPolicy prises durant ce cycle, absentes du rapport jusqu'ici alors qu'elles doivent
    # elles aussi être appliquées par l'équipe réseau. Entièrement masquée si `policies` est
    # vide (contrairement à la section flux ci-dessus qui garde son placeholder) : même principe
    # que "aucun changement de règle", demande explicite de l'encadrant.
    if policies:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 7, "Politiques de sous-reseau decidees durant ce cycle", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(
            0, 7, f"{len(policies)} politique(s) de sous-reseau decidee(s) durant ce cycle",
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 9)
        with pdf.table(text_align="LEFT") as table:
            header = table.row()
            for label in ("CIDR source", "Destination", "Port", "Action", "Decide par", "Date"):
                header.cell(label)
            for policy in policies:
                row = table.row()
                row.cell(policy.src_cidr)
                row.cell(policy.destination)
                row.cell(str(policy.dst_port) if policy.dst_port is not None else "any")
                row.cell(policy.action or "-")
                row.cell(policy.decided_by or "-")
                row.cell(policy.created_at.strftime("%Y-%m-%d"))

        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Detail par decision", new_x="LMARGIN", new_y="NEXT")
        for policy in policies:
            # Même mécanisme que la boucle "Detail par decision" des flux ci-dessus (phrase
            # structurée en tête, justification en complément, new_x/new_y explicites pour la
            # même raison -- voir le commentaire détaillé plus haut dans cette fonction).
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(
                0, 5,
                _network_policy_narrative_sentence(policy.src_cidr, policy.destination, policy.dst_port, policy.action),
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, policy.justification or "(aucune)", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    return bytes(pdf.output())


def build_network_policy_pdf(policy: NetworkPolicy) -> bytes:
    """Fiche d'une politique de sous-réseau (2026-09-10, demande de l'encadrant) -- même style
    que les autres fiches (titre, phrase structurée en tête, tableau, justification en
    complément), mais SANS AUCUN lien avec un Flow/FlowValidationHistory précis : NetworkPolicy
    porte tous ses propres champs, rien à aller chercher ailleurs.
    """
    pdf = NouvelairPDF()
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


# --- Guide technique : conversion Markdown -> PDF (2026-09-15, demande de l'encadrant, dernier
# jour de stage) -----------------------------------------------------------------------------
#
# `docs/GUIDE-TECHNIQUE.md` reste la SEULE source de vérité du contenu -- ce module ne fait que
# le mettre en forme dans le gabarit `NouvelairPDF` déjà partagé par toutes les fiches ci-dessus,
# jamais une deuxième copie du texte. Un sous-ensemble volontairement limité de Markdown est
# supporté (titres ATX, listes à puces/numérotées, blocs de code barrière, citations, tables
# "pipe" simples, gras/code en ligne) -- exactement ce qu'utilise le guide réel, pas un moteur
# Markdown générique : la priorité explicite de l'encadrant est la fiabilité avant l'exhaustivité,
# un jour avant la fin du stage.

# Police coeur (Helvetica/Courier) : encodage latin-1 uniquement (`core_fonts_encoding`,
# confirmé en testant -- un caractère hors de ce jeu, ex. "oe" ligaturé ou un vrai tiret
# cadratin "—", lève `FPDFUnicodeEncodingException` et ferait échouer toute la génération).
# Le reste du projet contourne ça en évitant ces caractères dans SES propres chaînes PDF (ex.
# "cloture" sans accent) ; le guide, lui, est rédigé en français normal avec accents (accents
# simples eacute/egrave/ecirc/agrave/ccedil... RESTENT dans le jeu latin-1, donc affichés tels
# quels). Ce filet de sécurité ne fait que remplacer la poignée de caractères hors latin-1
# réellement susceptibles d'apparaître dans un Markdown écrit normalement (tiret cadratin/demi-
# cadratin, points de suspension, puces typographiques, guillemets courbes, flèches, ligature
# "œ") -- et, en dernier recours, n'importe quel autre caractère imprévu -- plutôt que de laisser
# la génération planter sur un caractère isolé.
_PDF_CHAR_REPLACEMENTS = {
    "—": "--", "–": "-", "…": "...", "•": "-", "·": "-",
    "→": "->", "←": "<-", "‘": "'", "’": "'", "“": '"', "”": '"',
    "œ": "oe", "Œ": "OE",
}


def _pdf_safe(text: str) -> str:
    for src, dst in _PDF_CHAR_REPLACEMENTS.items():
        text = text.replace(src, dst)
    # Marqueurs Markdown résiduels : `_write_inline()` les retire déjà lui-même en isolant le
    # contenu de chaque segment AVANT d'appeler `_pdf_safe()` (donc sans effet sur son propre
    # texte) -- ce nettoyage ne sert qu'aux textes qui ne passent PAS par `_write_inline()`
    # (titres, citations) : un bug réel trouvé en vérifiant (2026-09-15) laissait des ``backtick``
    # et des **doubles astérisques** littéraux s'afficher tels quels dans ces deux cas.
    text = text.replace("`", "").replace("**", "")
    # Filet de sécurité final : tout caractère encore hors latin-1 (emoji, symbole rare...)
    # remplacé par son équivalent ASCII le plus proche si connu, sinon tout simplement retiré --
    # jamais une exception qui ferait échouer tout le document pour un seul caractère imprévu.
    return text.encode("latin-1", errors="ignore").decode("latin-1")


# Un seul niveau de gras (`**...**`) et de code en ligne (`` `...` ``), jamais imbriqués --
# suffisant pour le guide réel, pas un vrai tokenizer Markdown. `re.split` avec un groupe
# capturant conserve les séparateurs eux-mêmes dans la liste résultante.
_INLINE_TOKEN_RE = re.compile(r"(\*\*.+?\*\*|`.+?`)")


def _write_inline(pdf: FPDF, text: str, line_height: float, size: int = 10) -> None:
    """Écrit une ligne de texte avec gras/code en ligne, en laissant fpdf2 gérer le retour à la
    ligne automatique (`write()`, contrairement à `multi_cell()`, poursuit sur la même ligne
    visuelle d'un appel à l'autre -- c'est ce qui permet de mélanger plusieurs styles sur un
    même paragraphe). Retombe TOUJOURS sur Helvetica normal en sortie, pour ne jamais laisser
    un style de segment "fuir" sur l'appel suivant.
    """
    for token in _INLINE_TOKEN_RE.split(text):
        if not token:
            continue
        if token.startswith("**") and token.endswith("**") and len(token) >= 4:
            pdf.set_font("Helvetica", "B", size)
            pdf.write(line_height, _pdf_safe(token[2:-2]))
        elif token.startswith("`") and token.endswith("`") and len(token) >= 2:
            pdf.set_font("Courier", "", size - 1)
            pdf.write(line_height, _pdf_safe(token[1:-1]))
        else:
            pdf.set_font("Helvetica", "", size)
            pdf.write(line_height, _pdf_safe(token))
    pdf.set_font("Helvetica", "", size)
    pdf.ln(line_height)


_ATX_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_UNORDERED_ITEM_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def _render_table(pdf: FPDF, rows: list[list[str]]) -> None:
    """Table Markdown "pipe" (`| a | b |`) -- réutilise `pdf.table()`, déjà utilisée pour les
    tableaux du rapport de clôture de cycle plus haut dans ce fichier, jamais une deuxième
    façon de dessiner un tableau."""
    pdf.set_font("Helvetica", "", 9)
    with pdf.table(text_align="LEFT") as table:
        for i, cells in enumerate(rows):
            row = table.row()
            for cell in cells:
                row.cell(_pdf_safe(cell.strip()))
            if i == 0:
                pdf.set_font("Helvetica", "", 9)  # l'en-tête est mis en gras par pdf.table() lui-même


def _render_markdown_body(pdf: FPDF, markdown_text: str) -> None:
    lines = markdown_text.splitlines()
    i = 0
    n = len(lines)
    in_code_block = False
    code_buffer: list[str] = []
    table_buffer: list[list[str]] = []

    # Sommaire cliquable (2026-09-15, demande de l'encadrant -- un lien si fpdf2 le permet
    # facilement, un simple texte numéroté sinon : `add_link()`/`set_link()` couvrent le cas
    # exactement, retenu). Un lien par section de niveau 2 (`## ...`), SAUF "Sommaire"
    # elle-même (rien à lier vers son propre sommaire). `add_link()` réserve un identifiant
    # MAINTENANT, avant tout rendu -- sa vraie destination (page/position) n'est fixée que
    # plus bas, via `set_link()`, au moment où la boucle principale atteint réellement cette
    # section. C'est cette réservation à l'avance qui permet à la liste du sommaire (tout en
    # haut du document) de pointer vers du contenu pas encore dessiné.
    toc_link_ids: list[int] = [
        pdf.add_link()
        for raw in lines
        if (m := _ATX_HEADER_RE.match(raw.strip())) and len(m.group(1)) == 2 and m.group(2).strip() != "Sommaire"
    ]
    in_toc_section = False
    toc_entry_index = 0
    section_bind_index = 0

    def flush_code_block() -> None:
        nonlocal code_buffer
        if not code_buffer:
            return
        pdf.set_fill_color(245, 245, 243)
        pdf.set_font("Courier", "", 8)
        for code_line in code_buffer:
            # multi_cell (pas cell) : filet de sécurité si une ligne dépasse malgré tout la
            # largeur de page (mesuré à l'écriture du guide, la ligne la plus longue tient en
            # Courier 8 -- multi_cell empêche simplement toute exception si ce n'était plus vrai
            # après une future modification du guide, en repliant la ligne plutôt que planter).
            # new_x="LMARGIN", new_y="NEXT" explicites -- même piège fpdf2 déjà documenté plus
            # haut dans ce fichier (build_cycle_report_pdf) : sans ça, le x ne revient pas à la
            # marge gauche entre deux multi_cell() consécutifs, et la largeur disponible finit
            # par tomber à zéro (`FPDFException: Not enough horizontal space...`).
            pdf.multi_cell(0, 4.3, _pdf_safe(code_line) or " ", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(2)
        code_buffer = []

    def flush_table() -> None:
        nonlocal table_buffer
        if not table_buffer:
            return
        _render_table(pdf, table_buffer)
        pdf.ln(2)
        table_buffer = []

    while i < n:
        raw_line = lines[i]
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                flush_code_block()
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            code_buffer.append(raw_line.rstrip("\n"))
            i += 1
            continue

        if _TABLE_ROW_RE.match(raw_line):
            if _TABLE_SEPARATOR_RE.match(raw_line) and table_buffer:
                i += 1
                continue  # ligne de séparation d'en-tête ("|---|---|") -- jamais une vraie ligne
            table_buffer.append(_TABLE_ROW_RE.match(raw_line).group(1).split("|"))
            i += 1
            continue
        if table_buffer:
            flush_table()

        if not stripped:
            pdf.ln(2)
            i += 1
            continue

        header_match = _ATX_HEADER_RE.match(stripped)
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2)
            size = {1: 17, 2: 13, 3: 11}[level]
            pdf.ln(3 if level > 1 else 1)
            pdf.set_font("Helvetica", "B", size)
            if level == 2:
                in_toc_section = title.strip() == "Sommaire"
                if not in_toc_section and section_bind_index < len(toc_link_ids):
                    # Cible réelle du lien réservé plus haut, maintenant qu'on rend
                    # effectivement cette section -- même ordre de parcours que le pré-scan,
                    # donc le Nᵉ lien réservé correspond toujours à la Nᵉ section rencontrée ici.
                    pdf.set_link(toc_link_ids[section_bind_index], y=pdf.get_y(), page=pdf.page_no())
                    section_bind_index += 1
            pdf.multi_cell(0, size * 0.5, _pdf_safe(title))
            pdf.ln(1)
            i += 1
            continue

        if stripped in ("---", "___", "***"):
            pdf.ln(1)
            pdf.set_draw_color(210, 210, 210)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.set_draw_color(0, 0, 0)
            pdf.ln(3)
            i += 1
            continue

        if stripped.startswith("> "):
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(110, 110, 110)
            pdf.multi_cell(0, 5, _pdf_safe(stripped[2:]))
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 10)
            pdf.ln(2)
            i += 1
            continue

        ordered_match = _ORDERED_ITEM_RE.match(raw_line)
        unordered_match = _UNORDERED_ITEM_RE.match(raw_line)
        if ordered_match or unordered_match:
            prefix = f"{ordered_match.group(1)}. " if ordered_match else "-  "
            body = ordered_match.group(2) if ordered_match else unordered_match.group(1)
            pdf.set_x(pdf.l_margin + 4)
            pdf.set_font("Helvetica", "", 10)
            pdf.write(5, prefix)
            if in_toc_section and ordered_match and toc_entry_index < len(toc_link_ids):
                # Entrée de sommaire cliquable -- couleur lien classique le temps de ce seul
                # segment, jamais laissée "fuir" sur le texte suivant.
                pdf.set_text_color(30, 90, 170)
                pdf.write(5, _pdf_safe(body), link=toc_link_ids[toc_entry_index])
                pdf.set_text_color(0, 0, 0)
                pdf.ln(5)
                toc_entry_index += 1
            else:
                _write_inline(pdf, body, 5)
            i += 1
            continue

        _write_inline(pdf, stripped, 5.2)
        i += 1

    flush_code_block()
    flush_table()


def build_technical_guide_pdf(markdown_text: str) -> bytes:
    """Guide technique de passation (2026-09-15, dernier jour de stage, demande de l'encadrant)
    -- convertit `docs/GUIDE-TECHNIQUE.md` (seule source de vérité du contenu, synthétisée à la
    main à partir de toute la documentation du projet) dans le même gabarit `NouvelairPDF` que
    les autres fiches -- pas une mise en page différente. Prend le Markdown déjà lu en chaîne
    (jamais ce module lui-même qui va chercher le fichier sur disque -- cohérent avec le reste
    de ce fichier, qui reçoit toujours des données déjà résolues par l'appelant).
    """
    pdf = NouvelairPDF()
    pdf.set_title(TECHNICAL_GUIDE_TITLE)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    _render_markdown_body(pdf, markdown_text)
    return bytes(pdf.output())

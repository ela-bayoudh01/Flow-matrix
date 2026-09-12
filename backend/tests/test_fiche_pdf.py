"""_narrative_sentence() -- phrase structurée systématique (2026-09-10, demande de
l'encadrant), testée directement en tant que fonction pure plutôt qu'en extrayant le texte
d'un PDF généré (fpdf2 n'expose pas de moyen fiable de relire le texte rendu -- la validité du
PDF lui-même, elle, reste couverte par les tests d'API existants sur chaque endpoint fiche).
"""

from app.fiche_pdf import _narrative_sentence, _network_policy_narrative_sentence


def test_narrative_sentence_allow():
    assert (
        _narrative_sentence("10.10.1.1", "203.0.113.10", 443, "Allow")
        == "Le trafic de 10.10.1.1 vers 203.0.113.10 sera Autorise sur le port 443."
    )


def test_narrative_sentence_block():
    assert (
        _narrative_sentence("10.10.1.1", "203.0.113.10", 445, "Block")
        == "Le trafic de 10.10.1.1 vers 203.0.113.10 sera Bloque sur le port 445."
    )


def test_narrative_sentence_no_port():
    # dst_port=None (ex. ICMP) -- jamais "sur le port None", un texte lisible à la place.
    assert (
        _narrative_sentence("10.10.1.1", "203.0.113.10", None, "Block")
        == "Le trafic de 10.10.1.1 vers 203.0.113.10 sera Bloque sur le port tout port."
    )


def test_narrative_sentence_unknown_action_falls_back_to_the_raw_value():
    # Jamais une exception ni un texte vide si l'action ne correspond à aucun mapping connu --
    # affiche la valeur brute plutôt que de cacher un cas inattendu.
    assert (
        _narrative_sentence("10.10.1.1", "203.0.113.10", 443, "Mixed")
        == "Le trafic de 10.10.1.1 vers 203.0.113.10 sera Mixed sur le port 443."
    )


def test_narrative_sentence_none_action():
    assert (
        _narrative_sentence("10.10.1.1", "203.0.113.10", 443, None)
        == "Le trafic de 10.10.1.1 vers 203.0.113.10 sera (action non renseignee) sur le port 443."
    )


# --- _network_policy_narrative_sentence (2026-09-10, politiques de sous-réseau) ------------


def test_network_policy_narrative_sentence_block():
    assert (
        _network_policy_narrative_sentence("10.10.1.0/24", "Internet_Zone", 443, "Block")
        == "Tout le trafic depuis 10.10.1.0/24 vers Internet_Zone sera Bloque sur le port 443."
    )


def test_network_policy_narrative_sentence_allow_no_port():
    assert (
        _network_policy_narrative_sentence("10.10.1.0/24", "203.0.113.0/28", None, "Allow")
        == "Tout le trafic depuis 10.10.1.0/24 vers 203.0.113.0/28 sera Autorise sur le port tout port."
    )

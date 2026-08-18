"""Lignes de log utilisées par les tests. Format Cisco FTD réel (syslog clé:valeur), mais
**toutes les valeurs identifiantes sont fictives** : IP internes (plages 10.10.0.0/16 et
10.20.0.0/16, distinctes de toute plage réelle Nouvelair), IP externes (plage documentaire
RFC 5737 203.0.113.0/24 / 198.51.100.0/24, jamais routées sur Internet), DeviceUUID, noms de
policy ACL (`SITE-A-FWTEST`, `SITE-B-FWTEST`) et de zones spécifiques (`DMZ_Zone`, `OPS_Zone`,
`Branch_Users_Zone`). Voir docs/01-journal-technique.md (copie locale, non versionnée) pour
la table de correspondance avec les données réelles d'origine ayant servi à calibrer le format.
"""

# --- Site A fictif (ACPolicy = SITE-A-FWTEST) ---

ALLOW_HTTPS_LINE = (
    "Jun 28 23:34:06 10.10.64.254  : %FTD-6-430003: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000001, InstanceID: 1, "
    "FirstPacketSecond: 2026-06-28T23:23:56Z, ConnectionID: 50437, "
    "AccessControlRuleAction: Allow, SrcIP: 10.10.1.32, DstIP: 203.0.113.10, "
    "SrcPort: 59941, DstPort: 443, Protocol: tcp, IngressInterface: USER, "
    "EgressInterface: INTERNET, IngressZone: Users_Zone, EgressZone: Internet_Zone, "
    "IngressVRF: Global, EgressVRF: Global, ACPolicy: SITE-A-FWTEST, "
    "AccessControlRuleName: ACL_ANY_INTERNET_HTTPS_OUT, Prefilter Policy: Default Prefilter Policy, "
    "Client: SSL client, ApplicationProtocol: HTTPS, WebApplication: Kaspersky, "
    "ConnectionDuration: 610, InitiatorPackets: 35, ResponderPackets: 21, "
    "InitiatorBytes: 1423, ResponderBytes: 9856, NAPPolicy: Balanced Security and Connectivity, "
    "URLCategory: Computer Security, URLReputation: Trusted, URL: https://ds.kaspersky.com, "
    "NAT_InitiatorPort: 59941, NAT_ResponderPort: 443, NAT_InitiatorIP: 203.0.113.1, "
    "NAT_ResponderIP: 203.0.113.10, ClientAppDetector: AppID"
)

# Variante SYNTHÉTIQUE de la ligne ci-dessus (ConnectionID/InstanceID/FirstPacketSecond/volumes
# modifiés) pour simuler une 2e observation de la même communication -- teste l'agrégation
# du Flow Engine (occurrence_count, sommes). Même paire (SrcIP, DstIP, DstPort, Protocol).
ALLOW_HTTPS_LINE_REPEAT = (
    "Jun 28 23:40:12 10.10.64.254  : %FTD-6-430003: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000001, InstanceID: 7, "
    "FirstPacketSecond: 2026-06-28T23:40:12Z, ConnectionID: 50501, "
    "AccessControlRuleAction: Allow, SrcIP: 10.10.1.32, DstIP: 203.0.113.10, "
    "SrcPort: 60210, DstPort: 443, Protocol: tcp, IngressInterface: USER, "
    "EgressInterface: INTERNET, IngressZone: Users_Zone, EgressZone: Internet_Zone, "
    "IngressVRF: Global, EgressVRF: Global, ACPolicy: SITE-A-FWTEST, "
    "AccessControlRuleName: ACL_ANY_INTERNET_HTTPS_OUT, Prefilter Policy: Default Prefilter Policy, "
    "Client: SSL client, ApplicationProtocol: HTTPS, WebApplication: Kaspersky, "
    "ConnectionDuration: 300, InitiatorPackets: 10, ResponderPackets: 8, "
    "InitiatorBytes: 500, ResponderBytes: 4000, NAPPolicy: Balanced Security and Connectivity, "
    "ClientAppDetector: AppID"
)

BLOCK_SMB_LINE = (
    "Jun 28 23:34:09 10.10.64.254  : %FTD-6-430002: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000001, InstanceID: 3, "
    "FirstPacketSecond: 2026-06-28T23:34:09Z, ConnectionID: 50468, "
    "AccessControlRuleAction: Block, SrcIP: 10.11.1.193, DstIP: 10.12.1.100, "
    "SrcPort: 4025, DstPort: 139, Protocol: tcp, IngressInterface: DMZ, "
    "EgressInterface: OPS, IngressZone: DMZ_Zone, EgressZone: OPS_Zone, "
    "IngressVRF: Global, EgressVRF: Global, ACPolicy: SITE-A-FWTEST, "
    "AccessControlRuleName: Default Action, Prefilter Policy: Default Prefilter Policy, "
    "InitiatorPackets: 0, ResponderPackets: 0, InitiatorBytes: 0, ResponderBytes: 0, "
    "NAPPolicy: Balanced Security and Connectivity, ClientAppDetector: AppID"
)

# --- Site B fictif (ACPolicy = SITE-B-FWTEST) ---

SITE_B_ALLOW_LINE = (
    "Jun 28 23:34:05 10.20.64.254  : %FTD-6-430003: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000002, InstanceID: 3, "
    "FirstPacketSecond: 2026-06-28T23:31:14Z, ConnectionID: 37623, "
    "AccessControlRuleAction: Allow, SrcIP: 10.20.8.1, DstIP: 198.51.100.20, "
    "SrcPort: 65461, DstPort: 443, Protocol: tcp, IngressInterface: Branch_Users, "
    "EgressInterface: Internet, IngressZone: Branch_Users_Zone, EgressZone: Internet_Zone, "
    "IngressVRF: Global, EgressVRF: Global, ACPolicy: SITE-B-FWTEST, "
    "AccessControlRuleName: ACL_ANY_INTERNET_HTTPS_OUT, Prefilter Policy: Default Prefilter Policy, "
    "Client: SSL client, ApplicationProtocol: HTTPS, WebApplication: Mozilla, "
    "ConnectionDuration: 171, InitiatorPackets: 21, ResponderPackets: 26, "
    "InitiatorBytes: 2688, ResponderBytes: 7872, NAPPolicy: Balanced Security and Connectivity, "
    "SSLPolicy: None, SSLFlowStatus: Success, SSLCipherSuite: Unknown, "
    "SSLCertificate: 0000000000000000000000000000000000aaaa, SSLVersion: Unknown, "
    "SSLServerCertStatus: Valid, SSLActualAction: Do Not Decrypt, SSLExpectedAction: Do Not Decrypt, "
    "URLCategory: Computers and Internet, URLReputation: Favorable, "
    "URL: https://merino.services.mozilla.com, NAT_InitiatorPort: 65461, NAT_ResponderPort: 443, "
    "NAT_InitiatorIP: 203.0.113.2, NAT_ResponderIP: 198.51.100.20, ClientAppDetector: AppID"
)

ICMP_BLOCK_LINE = (
    "Jun 29 00:12:49 10.20.64.254  : %FTD-6-430002: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000002, InstanceID: 2, "
    "FirstPacketSecond: 2026-06-29T00:12:49Z, ConnectionID: 57183, "
    "AccessControlRuleAction: Block, SrcIP: 10.20.253.61, DstIP: 10.21.32.23, "
    "ICMPType: Destination Unreachable, ICMPCode: Port unreachable, Protocol: icmp, "
    "ACPolicy: SITE-B-FWTEST, AccessControlRuleName: Default Action, "
    "Prefilter Policy: Default Prefilter Policy, InitiatorPackets: 1, ResponderPackets: 0, "
    "InitiatorBytes: 122, ResponderBytes: 0, NAPPolicy: Balanced Security and Connectivity, "
    "VLAN_ID: 253, ClientAppDetector: AppID"
)

# --- Ligne construite (cas jamais observé en réel) : ACPolicy absent, pour tester le
# fallback sur le nom de fichier (décision de Loulou, 2026-08-11). ---

NO_AC_POLICY_LINE = (
    "Jun 28 23:34:06 10.10.64.254  : %FTD-6-430003: EventPriority: Low, "
    "DeviceUUID: 00000000-0000-4000-a000-000000000001, InstanceID: 9, "
    "FirstPacketSecond: 2026-06-28T23:45:00Z, ConnectionID: 50600, "
    "AccessControlRuleAction: Allow, SrcIP: 10.10.1.40, DstIP: 8.8.8.8, "
    "SrcPort: 55000, DstPort: 443, Protocol: tcp, AccessControlRuleName: ACL_ANY_INTERNET_HTTPS_OUT, "
    "InitiatorPackets: 5, ResponderPackets: 5, InitiatorBytes: 100, ResponderBytes: 100"
)

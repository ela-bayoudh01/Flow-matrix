import { useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import MenuItem from "@mui/material/MenuItem";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import type { FlowFilterValues } from "../../api/types";
import { useZoneOptions } from "../../hooks/useZoneOptions";

const ACTION_OPTIONS = ["Allow", "Block", "Mixed"];
const PROTOCOL_OPTIONS = ["tcp", "udp", "icmp", "ipv6-icmp"];
// "non_qualifie" n'est pas une vraie valeur de criticality_label (NULL en base) -- ne pas
// l'ajouter ici, un filtre d'égalité dessus ne matcherait jamais rien.
const CRITICALITY_OPTIONS = ["low", "medium", "high", "critical"];
const VALIDATION_STATUS_OPTIONS = ["pending", "approved", "blocked"];

interface FilterBarProps {
  value: FlowFilterValues;
  onChange: (filters: FlowFilterValues) => void;
}

export function FilterBar({ value, onChange }: FilterBarProps) {
  const [showMore, setShowMore] = useState(false);
  const zoneOptions = useZoneOptions();

  function set<K extends keyof FlowFilterValues>(key: K, raw: string) {
    onChange({ ...value, [key]: raw === "" ? undefined : raw });
  }

  function setNumber<K extends keyof FlowFilterValues>(key: K, raw: string) {
    const parsed = raw === "" ? undefined : Number(raw);
    onChange({ ...value, [key]: (Number.isNaN(parsed) ? undefined : parsed) as FlowFilterValues[K] });
  }

  const hasAnyFilter = Object.values(value).some((v) => v !== undefined && v !== "");

  return (
    <Box sx={{ mb: 2 }}>
      {/* Ordre de priorité demandé : zone > action > protocole/port > criticité */}
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <TextField
          select
          size="small"
          label="Zone source"
          value={value.ingress_zone ?? ""}
          onChange={(e) => set("ingress_zone", e.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Toutes</MenuItem>
          {zoneOptions.map((z) => (
            <MenuItem key={z} value={z}>
              {z}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Zone destination"
          value={value.egress_zone ?? ""}
          onChange={(e) => set("egress_zone", e.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">Toutes</MenuItem>
          {zoneOptions.map((z) => (
            <MenuItem key={z} value={z}>
              {z}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Action"
          value={value.dominant_action ?? ""}
          onChange={(e) => set("dominant_action", e.target.value)}
          sx={{ minWidth: 130 }}
        >
          <MenuItem value="">Toutes</MenuItem>
          {ACTION_OPTIONS.map((a) => (
            <MenuItem key={a} value={a}>
              {a}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          select
          size="small"
          label="Protocole"
          value={value.protocol ?? ""}
          onChange={(e) => set("protocol", e.target.value)}
          sx={{ minWidth: 130 }}
        >
          <MenuItem value="">Tous</MenuItem>
          {PROTOCOL_OPTIONS.map((p) => (
            <MenuItem key={p} value={p}>
              {p}
            </MenuItem>
          ))}
        </TextField>

        <TextField
          size="small"
          label="Port"
          type="number"
          value={value.dst_port ?? ""}
          onChange={(e) => setNumber("dst_port", e.target.value)}
          sx={{ width: 110 }}
        />

        <TextField
          select
          size="small"
          label="Criticité"
          value={value.criticality_label ?? ""}
          onChange={(e) => set("criticality_label", e.target.value)}
          sx={{ minWidth: 130 }}
        >
          <MenuItem value="">Toutes</MenuItem>
          {CRITICALITY_OPTIONS.map((c) => (
            <MenuItem key={c} value={c}>
              {c}
            </MenuItem>
          ))}
        </TextField>

        <Button size="small" onClick={() => setShowMore((s) => !s)}>
          {showMore ? "Moins de filtres" : "Plus de filtres"}
        </Button>

        {hasAnyFilter && (
          <Button size="small" color="secondary" onClick={() => onChange({})}>
            Réinitialiser
          </Button>
        )}
      </Stack>

      <Collapse in={showMore}>
        <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: "wrap", mt: 2 }}>
          <TextField
            size="small"
            label="IP source"
            value={value.src_ip ?? ""}
            onChange={(e) => set("src_ip", e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label="IP destination"
            value={value.dst_ip ?? ""}
            onChange={(e) => set("dst_ip", e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label="Application"
            value={value.web_application ?? ""}
            onChange={(e) => set("web_application", e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <TextField
            size="small"
            label="Source (site)"
            value={value.source ?? ""}
            onChange={(e) => set("source", e.target.value)}
            sx={{ minWidth: 160 }}
            helperText="Nom exact, cf. ACPolicy"
          />
          <TextField
            select
            size="small"
            label="Statut de validation"
            value={value.validation_status ?? ""}
            onChange={(e) => set("validation_status", e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">Tous</MenuItem>
            {VALIDATION_STATUS_OPTIONS.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </Collapse>
    </Box>
  );
}

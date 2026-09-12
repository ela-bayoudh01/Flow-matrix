import { useEffect, useState } from "react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import IconButton from "@mui/material/IconButton";
import SearchIcon from "@mui/icons-material/Search";
import ClearIcon from "@mui/icons-material/Clear";

interface KeywordSearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

// Un seul composant, réutilisé identiquement sur les 5 pages qui listent des flux/entités
// (Table des flux, Cycle de validation, Historique, Recommandations, Propositions ACL) --
// demande explicite de l'encadrant (2026-08-25) : une vraie recherche par mot-clé, pas
// recodée différemment page par page. La recherche elle-même (quelles colonnes, sur quelle
// table) vit côté backend (app/search_utils.py) -- ce composant n'est qu'un champ de saisie
// debouncé, jamais de logique de filtrage ici.
//
// Debounce ~300 ms : évite une requête réseau à chaque frappe. `draft` est l'état visuel
// immédiat (jamais de lag à la frappe), `value`/`onChange` restent la source de vérité
// contrôlée par la page (permet un bouton "Réinitialiser" externe de vider le champ).
export function KeywordSearchField({ value, onChange, placeholder }: KeywordSearchFieldProps) {
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (draft !== value) onChange(draft);
    }, 300);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  return (
    <TextField
      size="small"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder={placeholder ?? "Rechercher (IP, zone, port, règle...)"}
      sx={{ minWidth: 260 }}
      slotProps={{
        input: {
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" color="action" />
            </InputAdornment>
          ),
          endAdornment: draft ? (
            <InputAdornment position="end">
              <IconButton size="small" onClick={() => setDraft("")} aria-label="Effacer la recherche">
                <ClearIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ) : undefined,
        },
      }}
    />
  );
}

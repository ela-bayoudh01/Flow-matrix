import { useEffect, useState } from "react";
import { useGridFilter, type CustomFilterProps } from "ag-grid-react";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import IconButton from "@mui/material/IconButton";
import ClearIcon from "@mui/icons-material/Clear";

// Filtre AG Grid simplifié (2026-09-11, demande de l'encadrant) : remplace le filtre par
// défaut d'AG Grid (menu "Contains/Equals/.../AND/OR") par un champ de recherche unique --
// même principe de simplicité que KeywordSearchField.tsx (la barre de recherche générale),
// mais par colonne, et appliqué sur Entrée plutôt que débounce (demande explicite : "je tape
// une valeur, j'appuie sur Entrée, ça filtre directement"). Toujours une correspondance
// "contient" insensible à la casse -- jamais de condition à choisir, jamais de bouton
// Apply/Clear/Reset (un filtre custom sans `enableFilterHandlers` remplace tout le contenu
// du popup, ces boutons n'existent que pour les filtres fournis par AG Grid). Voir
// FlowsTable.tsx, où ce composant remplace `filter: true` dans defaultColDef.
interface SimpleColumnFilterModel {
  value: string;
}

export function SimpleColumnFilter({ model, onModelChange, getValue }: CustomFilterProps<unknown, unknown, SimpleColumnFilterModel>) {
  const [draft, setDraft] = useState(model?.value ?? "");

  // Resynchronise si le modèle change depuis l'extérieur (ex. reset du filtre via l'API AG
  // Grid) -- même principe que KeywordSearchField.tsx.
  useEffect(() => setDraft(model?.value ?? ""), [model]);

  useGridFilter({
    doesFilterPass: (params) => {
      const value = getValue(params.node);
      if (value === null || value === undefined || value === "") return false;
      return String(value).toLowerCase().includes((model?.value ?? "").toLowerCase());
    },
    getModelAsString: (m) => m?.value ?? "",
  });

  function apply(nextValue: string) {
    const trimmed = nextValue.trim();
    onModelChange(trimmed ? { value: trimmed } : null);
  }

  return (
    <TextField
      size="small"
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") apply(draft);
      }}
      placeholder="Filtrer, puis Entrée"
      sx={{ m: 1, width: 200 }}
      slotProps={{
        input: {
          endAdornment: draft ? (
            <InputAdornment position="end">
              <IconButton
                size="small"
                aria-label="Effacer le filtre"
                onClick={() => {
                  setDraft("");
                  apply("");
                }}
              >
                <ClearIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ) : undefined,
        },
      }}
    />
  );
}

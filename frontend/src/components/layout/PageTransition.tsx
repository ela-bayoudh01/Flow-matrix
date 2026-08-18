import { type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import Fade from "@mui/material/Fade";
import Box from "@mui/material/Box";

// Cross-fade léger entre pages -- Fade MUI (déjà dans le projet), pas de librairie
// d'animation ajoutée. `key={pathname}` force un remount à chaque changement de route,
// ce qui redéclenche l'entrée -- volontairement discret (courte durée, pas de mouvement).
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <Fade in key={pathname} timeout={200}>
      <Box>{children}</Box>
    </Fade>
  );
}

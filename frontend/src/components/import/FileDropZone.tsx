import { useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";

interface FileDropZoneProps {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function FileDropZone({ onFileSelected, disabled }: FileDropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function openPicker() {
    if (!disabled) inputRef.current?.click();
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) onFileSelected(file);
  }

  return (
    <Box
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={openPicker}
      sx={{
        border: "2px dashed",
        borderColor: dragOver ? "primary.main" : "divider",
        borderRadius: 2,
        p: 4,
        textAlign: "center",
        cursor: disabled ? "default" : "pointer",
        backgroundColor: dragOver ? "rgba(42,120,214,0.06)" : "background.paper",
        opacity: disabled ? 0.6 : 1,
        transition: (t) => t.transitions.create(["background-color", "border-color"], { duration: t.transitions.duration.shortest }),
      }}
    >
      <input
        ref={inputRef}
        type="file"
        hidden
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelected(file);
          e.target.value = ""; // permet de resélectionner le même fichier ensuite
        }}
      />
      <CloudUploadOutlinedIcon fontSize="large" color="action" />
      <Typography variant="body1" sx={{ mt: 1 }}>
        Glissez-déposez un fichier de logs ici
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Format Cisco FTD, jusqu'à ~200 Mo
      </Typography>
      <Button
        variant="outlined"
        size="small"
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation(); // évite le double déclenchement avec le onClick de la zone
          openPicker();
        }}
      >
        Choisir un fichier
      </Button>
    </Box>
  );
}

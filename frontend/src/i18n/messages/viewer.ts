import { defineMessages } from "@/i18n/core"

// Zoomable viewer of a document page or a letter (`components/viewer.tsx`).
export const viewer = defineMessages({
  en: {
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    zoomReset: "Fit to width",
    fitPage: "Whole page",
    zoomHint: "Ctrl + wheel to zoom, drag to move around",
    open: "Open the document",
    enlarge: "Enlarge",
    pane: "Page",
    keysHint: "+ and − to zoom, 0 to fit to width, arrow keys to move around",
    zoomLevel: "Zoom {value}, fit to width",
  },
  fr: {
    zoomIn: "Agrandir",
    zoomOut: "Réduire",
    zoomReset: "Ajuster à la largeur",
    fitPage: "Page entière",
    zoomHint: "Ctrl + molette pour zoomer, glisser pour se déplacer",
    open: "Ouvrir le document",
    enlarge: "Agrandir",
    pane: "Page",
    keysHint: "+ et − pour zoomer, 0 pour ajuster à la largeur, flèches pour se déplacer",
    zoomLevel: "Zoom {value}, ajuster à la largeur",
  },
})

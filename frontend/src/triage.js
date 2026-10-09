// Une ligne a été corrigée si l'humain a changé la catégorie ou la priorité proposée par l'IA
export const isCorrected = (row) => row.category !== row.suggestedCategory || row.priority !== row.suggestedPriority;

// L'IA doute : catégorie ou priorité sous le seuil de confiance
export const lowConfidence = (row, threshold) =>
  row.category_confidence < threshold || (row.priority_confidence != null && row.priority_confidence < threshold);

export const rowStatus = (row, threshold) => {
  if (row.validated) return isCorrected(row) ? 'corrigé' : 'validé';
  return lowConfidence(row, threshold) ? 'à relire' : 'sûr';
};

// Une ligne a été corrigée si l'humain a changé la catégorie ou la priorité proposée
export const isCorrected = (row) => row.category !== row.suggestedCategory || row.priority !== row.suggestedPriority;

// L'IA doute de la catégorie : confiance sous le seuil
export const lowConfidence = (row, threshold) => row.category_confidence < threshold;

// À relire : catégorie douteuse, ou priorité la plus haute (un humain valide toujours les urgences)
export const needsReview = (row, threshold, topPriority) =>
  lowConfidence(row, threshold) || (!!topPriority && row.priority === topPriority);

export const rowStatus = (row, threshold, topPriority) => {
  if (row.validated) return isCorrected(row) ? 'corrigé' : 'validé';
  return needsReview(row, threshold, topPriority) ? 'à relire' : 'sûr';
};

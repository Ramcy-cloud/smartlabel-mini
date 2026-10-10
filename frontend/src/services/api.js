import axios from 'axios';

// On crée une instance Axios pré-configurée pour pointer vers ton backend FastAPI
const apiClient = axios.create({
  baseURL: 'http://127.0.0.1:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const predictLabel = async (text, candidateLabels) => {
  try {
    const response = await apiClient.post('/predict', {
      text: text,
      candidate_labels: candidateLabels,
    });
    return response.data;
  } catch (error) {
    console.error("Erreur lors de la prédiction :", error);
    throw error;
  }
};

// Propose une catégorie (et une priorité) pour une liste de tickets
export const triageTickets = async (tickets, categories, priorities) => {
  const response = await apiClient.post('/triage', {
    tickets,
    categories,
    priorities: priorities && priorities.length ? priorities : null,
  });
  return response.data.results;
};

export const getLabelSets = async () => (await apiClient.get('/label-sets')).data;

export const saveLabelSet = async (name, labelSet) =>
  (await apiClient.put(`/label-sets/${encodeURIComponent(name)}`, labelSet)).data;

export const deleteLabelSet = async (name) => {
  await apiClient.delete(`/label-sets/${encodeURIComponent(name)}`);
};

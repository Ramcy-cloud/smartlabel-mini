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
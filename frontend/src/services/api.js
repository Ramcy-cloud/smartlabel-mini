import axios from 'axios';

// On crée une instance Axios pré-configurée pour pointer vers ton backend FastAPI
const apiClient = axios.create({
  baseURL: 'http://127.0.0.1:8000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Jeton de session : gardé le temps de l'onglet (sessionStorage), jamais dans le code ni dans l'URL
const TOKEN_KEY = 'smartlabel_token';
const store = () => {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
};
export const getToken = () => store()?.getItem(TOKEN_KEY) ?? null;
const setToken = (token) => store()?.setItem(TOKEN_KEY, token);
export const clearToken = () => store()?.removeItem(TOKEN_KEY);

let unauthorizedHandler = null;
// Appelé quand le serveur refuse le jeton (session expirée, backend redémarré)
export const onUnauthorized = (callback) => {
  unauthorizedHandler = callback;
};

apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Un 401 sans jeton (mauvais mot de passe à la connexion) n'est pas une session expirée
    if (error.response?.status === 401 && getToken()) {
      clearToken();
      unauthorizedHandler?.();
    }
    return Promise.reject(error);
  },
);

export const login = async (email, password) => {
  const { data } = await apiClient.post('/login', { email, password });
  setToken(data.token);
};

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
export const triageTickets = async (tickets, { categories, priorities, urgentKeywords, floors }) => {
  const response = await apiClient.post('/triage', {
    tickets,
    categories,
    priorities: priorities && priorities.length ? priorities : null,
    urgent_keywords: urgentKeywords ?? [],
    floors: floors ?? {},
  });
  return response.data.results;
};

export const getLabelSets = async () => (await apiClient.get('/label-sets')).data;

export const saveLabelSet = async (name, labelSet) =>
  (await apiClient.put(`/label-sets/${encodeURIComponent(name)}`, labelSet)).data;

export const deleteLabelSet = async (name) => {
  await apiClient.delete(`/label-sets/${encodeURIComponent(name)}`);
};

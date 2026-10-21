import axios from 'axios';

// Adresse du backend : fixée à la construction par VITE_API_BASE_URL (voir .env.example),
// sinon le backend local. Une image construite sans cette variable ne sert donc que pour un essai local.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api';

// On crée une instance Axios pré-configurée pour pointer vers le backend FastAPI
const apiClient = axios.create({
  baseURL: API_BASE_URL,
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

// Ferme la session côté serveur : le jeton devient inutilisable même s'il a été intercepté.
// Le jeton local est effacé dans tous les cas, y compris si le backend ne répond pas.
export const logout = async () => {
  try {
    if (getToken()) await apiClient.post('/logout');
  } catch {
    // La session sera de toute façon refusée ou expirera : rien à signaler à l'utilisateur
  } finally {
    clearToken();
  }
};

// Propose une catégorie (et une priorité) pour une liste de tickets
export const triageTickets = async (tickets, { categories, priorities, urgentKeywords, floors, descriptions, engine }) => {
  const response = await apiClient.post('/triage', {
    tickets,
    categories,
    priorities: priorities && priorities.length ? priorities : null,
    urgent_keywords: urgentKeywords ?? [],
    floors: floors ?? {},
    descriptions: descriptions ?? {},
    engine: engine ?? 'zero-shot',
  });
  return response.data.results;
};

// Moteurs de classification proposés pour ces catégories (local, entraîné, Mistral)
export const getEngines = async (categories) =>
  (await apiClient.get('/engines', { params: { categories }, paramsSerializer: { indexes: null } })).data;

export const getLabelSets = async () => (await apiClient.get('/label-sets')).data;

export const saveLabelSet = async (name, labelSet) =>
  (await apiClient.put(`/label-sets/${encodeURIComponent(name)}`, labelSet)).data;

export const deleteLabelSet = async (name) => {
  await apiClient.delete(`/label-sets/${encodeURIComponent(name)}`);
};

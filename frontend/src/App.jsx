import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Layout, Progress, Row, Slider, Space, Statistic, Switch, Typography, message } from 'antd';
import { LogoutOutlined } from '@ant-design/icons';
import { clearToken, deleteLabelSet, getLabelSets, getToken, onUnauthorized, saveLabelSet, triageTickets } from './services/api';
import { downloadCsv, toCsv } from './csv';
import LabelSetPanel from './components/LabelSetPanel';
import LoginScreen from './components/LoginScreen';
import TicketInput from './components/TicketInput';
import ResultsTable from './components/ResultsTable';
import { isCorrected, needsReview, rowStatus } from './triage';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const BATCH_SIZE = 10; // tickets par requête : permet d'afficher la progression
const DEFAULT_THRESHOLD = 75; // % de confiance sous lequel un humain doit relire

const apiError = (error, fallback) => error?.response?.data?.detail?.toString?.() ?? fallback;

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!getToken());
  const [sets, setSets] = useState({});
  const [currentSet, setCurrentSet] = useState(undefined);
  const [categories, setCategories] = useState([]);
  const [priorities, setPriorities] = useState([]);
  const [urgentKeywords, setUrgentKeywords] = useState([]);
  const [floors, setFloors] = useState({});
  const [savingSet, setSavingSet] = useState(false);

  const [tickets, setTickets] = useState([]);
  const [rows, setRows] = useState([]);
  // Catégories et priorités utilisées pour la dernière analyse : le tableau et l'export s'y réfèrent,
  // même si l'utilisateur modifie les listes ci-dessus ensuite
  const [runLabels, setRunLabels] = useState({ categories: [], priorities: [] });
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const [onlyReview, setOnlyReview] = useState(false);

  const applySet = useCallback((name, loaded) => {
    setCurrentSet(name);
    setCategories(loaded[name]?.categories ?? []);
    setPriorities(loaded[name]?.priorities ?? []);
    setUrgentKeywords(loaded[name]?.urgent_keywords ?? []);
    setFloors(loaded[name]?.floors ?? {});
  }, []);

  const resetWorkspace = useCallback(() => {
    setSets({});
    setCurrentSet(undefined);
    setCategories([]);
    setPriorities([]);
    setUrgentKeywords([]);
    setFloors({});
    setTickets([]);
    setRows([]);
  }, []);

  const handleLogout = useCallback(() => {
    clearToken();
    resetWorkspace();
    setIsAuthenticated(false);
  }, [resetWorkspace]);

  // Session refusée par le serveur : retour à l'écran de connexion
  useEffect(() => {
    onUnauthorized(() => {
      resetWorkspace();
      setIsAuthenticated(false);
      message.warning('Session expirée : reconnectez-vous.');
    });
  }, [resetWorkspace]);

  useEffect(() => {
    if (!isAuthenticated) return;
    getLabelSets()
      .then((loaded) => {
        setSets(loaded);
        const first = Object.keys(loaded)[0];
        if (first) applySet(first, loaded);
      })
      .catch(() => message.error("Impossible de charger les jeux de catégories. Vérifiez que le backend tourne."));
  }, [applySet, isAuthenticated]);

  // Une priorité minimale n'a de sens que pour une catégorie et une priorité encore présentes dans les listes
  const validFloors = () =>
    Object.fromEntries(Object.entries(floors).filter(([category, priority]) => categories.includes(category) && priorities.includes(priority)));

  const setFloor = (category, priority) =>
    setFloors((current) => {
      const next = { ...current };
      if (priority) next[category] = priority;
      else delete next[category];
      return next;
    });

  const handleSaveSet = async (name) => {
    setSavingSet(true);
    try {
      await saveLabelSet(name, { categories, priorities, urgent_keywords: urgentKeywords, floors: validFloors() });
      const loaded = await getLabelSets();
      setSets(loaded);
      setCurrentSet(name);
      message.success(`Jeu « ${name} » enregistré pour l'équipe.`);
    } catch (error) {
      message.error(apiError(error, "Enregistrement impossible : vérifiez les catégories (2 minimum, sans doublon)."));
    } finally {
      setSavingSet(false);
    }
  };

  const handleDeleteSet = async () => {
    try {
      await deleteLabelSet(currentSet);
      const loaded = await getLabelSets();
      setSets(loaded);
      const first = Object.keys(loaded)[0];
      if (first) applySet(first, loaded);
      else applySet(undefined, loaded);
      message.success('Jeu supprimé.');
    } catch (error) {
      message.error(apiError(error, 'Suppression impossible.'));
    }
  };

  const canRun = tickets.length > 0 && categories.length >= 2 && (priorities.length === 0 || priorities.length >= 2);

  const handleRun = async () => {
    const usedCategories = [...categories];
    const usedPriorities = [...priorities];
    const rules = { urgentKeywords: [...urgentKeywords], floors: validFloors() };
    setRunning(true);
    setProgress(0);
    setRows([]);
    setRunLabels({ categories: usedCategories, priorities: usedPriorities });
    const done = [];
    try {
      for (let i = 0; i < tickets.length; i += BATCH_SIZE) {
        const batch = tickets.slice(i, i + BATCH_SIZE);
        const results = await triageTickets(batch, { categories: usedCategories, priorities: usedPriorities, ...rules });
        results.forEach((r, j) =>
          done.push({
            ...r,
            key: i + j,
            suggestedCategory: r.category,
            suggestedPriority: r.priority,
            validated: false,
          }),
        );
        setRows([...done]);
        setProgress(Math.round((done.length / tickets.length) * 100));
      }
      message.success(`${done.length} tickets analysés.`);
    } catch (error) {
      const status = error?.response?.status;
      message.error(
        status === 429
          ? 'Trop de requêtes : patientez une minute puis relancez.'
          : apiError(error, `Analyse interrompue après ${done.length} tickets. Vérifiez que le backend tourne.`),
      );
    } finally {
      setRunning(false);
    }
  };

  const updateRow = (key, changes) => setRows((current) => current.map((r) => (r.key === key ? { ...r, ...changes } : r)));

  const t = threshold / 100;
  const topPriority = runLabels.priorities[0];
  const toReview = useMemo(() => rows.filter((r) => !r.validated && needsReview(r, t, topPriority)).length, [rows, t, topPriority]);
  const validated = useMemo(() => rows.filter((r) => r.validated).length, [rows]);
  const corrected = useMemo(() => rows.filter((r) => r.validated && isCorrected(r)).length, [rows]);
  const visibleRows = onlyReview ? rows.filter((r) => !r.validated && needsReview(r, t, topPriority)) : rows;

  const validateConfident = () => {
    setRows((current) => current.map((r) => (!r.validated && !needsReview(r, t, topPriority) ? { ...r, validated: true } : r)));
  };

  const handleExport = () => {
    const data = rows.map((r) => ({
      id: r.id ?? '',
      ticket: r.text,
      categorie: r.category,
      categorie_proposee_ia: r.suggestedCategory,
      ...(runLabels.priorities.length
        ? { priorite: r.priority, priorite_proposee: r.suggestedPriority, raisons_priorite: (r.priority_reasons ?? []).join(' ; ') }
        : {}),
      confiance_categorie: r.category_confidence,
      statut: rowStatus(r, t, topPriority),
    }));
    downloadCsv(`tickets-tries-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(data));
  };

  if (!isAuthenticated) {
    return <LoginScreen onSuccess={() => setIsAuthenticated(true)} />;
  }

  return (
    <Layout style={{ minHeight: '100vh', backgroundColor: '#f0f2f5' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          SmartLabel-Mini · Tri des tickets de support
        </Title>
        <Button type="text" icon={<LogoutOutlined />} onClick={handleLogout} style={{ color: 'white' }}>
          Déconnexion
        </Button>
      </Header>

      <Content style={{ padding: '24px', maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            title="L'IA propose, vous décidez."
            description={`L'IA propose la catégorie ; la priorité vient de règles que vous pouvez lire (survolez le « i » à côté de chaque priorité). Sous ${threshold} % de confiance, ou pour la priorité la plus haute, le ticket est marqué « à relire » : vérifiez-le avant de l'utiliser. Aucun texte n'est envoyé hors de votre infrastructure.`}
          />

          <Row gutter={[24, 24]}>
            <Col xs={24} lg={12}>
              <Card title="1. Catégories de tri" style={{ height: '100%' }}>
                <LabelSetPanel
                  sets={sets}
                  current={currentSet}
                  onSelect={(name) => applySet(name, sets)}
                  categories={categories}
                  priorities={priorities}
                  urgentKeywords={urgentKeywords}
                  floors={floors}
                  onChange={{ categories: setCategories, priorities: setPriorities, urgentKeywords: setUrgentKeywords, floor: setFloor }}
                  onSave={handleSaveSet}
                  onDelete={handleDeleteSet}
                  saving={savingSet}
                />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card title="2. Tickets à trier" style={{ height: '100%' }}>
                <TicketInput onLoad={(loaded) => { setTickets(loaded); setRows([]); }} />
                <Space style={{ marginTop: 8 }} wrap>
                  <Button type="primary" size="large" disabled={!canRun} loading={running} onClick={handleRun}>
                    Analyser {tickets.length ? `${tickets.length} ticket${tickets.length > 1 ? 's' : ''}` : ''}
                  </Button>
                  {tickets.length > 0 && !running && <Text type="secondary">{tickets.length} chargé(s)</Text>}
                </Space>
                {running && <Progress percent={progress} style={{ marginTop: 12 }} />}
              </Card>
            </Col>
          </Row>

          {rows.length > 0 && (
            <Card title="3. Résultats à valider">
              <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                <Row gutter={[16, 16]} align="middle">
                  <Col xs={12} md={4}><Statistic title="Analysés" value={rows.length} /></Col>
                  <Col xs={12} md={4}><Statistic title="À relire" value={toReview} styles={toReview ? { content: { color: '#d48806' } } : undefined} /></Col>
                  <Col xs={12} md={4}><Statistic title="Validés" value={validated} /></Col>
                  <Col xs={12} md={4}><Statistic title="Corrigés" value={corrected} /></Col>
                  <Col xs={24} md={8}>
                    <Text>Seuil de confiance : {threshold} %</Text>
                    <Slider min={50} max={95} step={5} value={threshold} onChange={setThreshold} />
                  </Col>
                </Row>

                <Space wrap>
                  <Button onClick={validateConfident}>Valider tous les cas sûrs</Button>
                  <Button type="primary" onClick={handleExport} disabled={running}>Exporter en CSV</Button>
                  <Switch checked={onlyReview} onChange={setOnlyReview} />
                  <Text>Afficher seulement les cas à relire</Text>
                </Space>

                {running && <Alert type="warning" showIcon title="Analyse en cours : le tableau se complète au fur et à mesure." />}

                <ResultsTable
                  rows={visibleRows}
                  threshold={t}
                  categories={runLabels.categories}
                  priorities={runLabels.priorities}
                  onUpdate={updateRow}
                />
              </Space>
            </Card>
          )}
        </Space>
      </Content>
    </Layout>
  );
}

export default App;

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Layout, Progress, Row, Slider, Space, Statistic, Switch, Typography, message } from 'antd';
import { deleteLabelSet, getLabelSets, saveLabelSet, triageTickets } from './services/api';
import { downloadCsv, toCsv } from './csv';
import LabelSetPanel from './components/LabelSetPanel';
import TicketInput from './components/TicketInput';
import ResultsTable from './components/ResultsTable';
import { isCorrected, lowConfidence, rowStatus } from './triage';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const BATCH_SIZE = 10; // tickets par requête : permet d'afficher la progression
const DEFAULT_THRESHOLD = 75; // % de confiance sous lequel un humain doit relire

const apiError = (error, fallback) => error?.response?.data?.detail?.toString?.() ?? fallback;

function App() {
  const [sets, setSets] = useState({});
  const [currentSet, setCurrentSet] = useState(undefined);
  const [categories, setCategories] = useState([]);
  const [priorities, setPriorities] = useState([]);
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
  }, []);

  useEffect(() => {
    getLabelSets()
      .then((loaded) => {
        setSets(loaded);
        const first = Object.keys(loaded)[0];
        if (first) applySet(first, loaded);
      })
      .catch(() => message.error("Impossible de charger les jeux de catégories. Vérifiez que le backend tourne."));
  }, [applySet]);

  const handleSaveSet = async (name) => {
    setSavingSet(true);
    try {
      await saveLabelSet(name, { categories, priorities });
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
    setRunning(true);
    setProgress(0);
    setRows([]);
    setRunLabels({ categories: usedCategories, priorities: usedPriorities });
    const done = [];
    try {
      for (let i = 0; i < tickets.length; i += BATCH_SIZE) {
        const batch = tickets.slice(i, i + BATCH_SIZE);
        const results = await triageTickets(batch, usedCategories, usedPriorities);
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
  const toReview = useMemo(() => rows.filter((r) => !r.validated && lowConfidence(r, t)).length, [rows, t]);
  const validated = useMemo(() => rows.filter((r) => r.validated).length, [rows]);
  const corrected = useMemo(() => rows.filter((r) => r.validated && isCorrected(r)).length, [rows]);
  const visibleRows = onlyReview ? rows.filter((r) => !r.validated && lowConfidence(r, t)) : rows;

  const validateConfident = () => {
    setRows((current) => current.map((r) => (!r.validated && !lowConfidence(r, t) ? { ...r, validated: true } : r)));
  };

  const handleExport = () => {
    const data = rows.map((r) => ({
      id: r.id ?? '',
      ticket: r.text,
      categorie: r.category,
      categorie_proposee_ia: r.suggestedCategory,
      ...(runLabels.priorities.length ? { priorite: r.priority, priorite_proposee_ia: r.suggestedPriority } : {}),
      confiance_categorie: r.category_confidence,
      ...(runLabels.priorities.length ? { confiance_priorite: r.priority_confidence } : {}),
      statut: rowStatus(r, t),
    }));
    downloadCsv(`tickets-tries-${new Date().toISOString().slice(0, 10)}.csv`, toCsv(data));
  };

  return (
    <Layout style={{ minHeight: '100vh', backgroundColor: '#f0f2f5' }}>
      <Header style={{ display: 'flex', alignItems: 'center', background: '#001529' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          SmartLabel-Mini · Tri des tickets de support
        </Title>
      </Header>

      <Content style={{ padding: '24px', maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="L'IA propose, vous décidez."
            description={`Chaque ticket reçoit une catégorie et une priorité suggérées. Sous ${threshold} % de confiance, le ticket est marqué « à relire » : vérifiez-le avant de l'utiliser. Aucun texte n'est envoyé hors de votre infrastructure.`}
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
                  onChange={{ categories: setCategories, priorities: setPriorities }}
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
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Row gutter={[16, 16]} align="middle">
                  <Col xs={12} md={4}><Statistic title="Analysés" value={rows.length} /></Col>
                  <Col xs={12} md={4}><Statistic title="À relire" value={toReview} valueStyle={toReview ? { color: '#d48806' } : undefined} /></Col>
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

                {running && <Alert type="warning" showIcon message="Analyse en cours : le tableau se complète au fur et à mesure." />}

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

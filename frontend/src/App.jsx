import { useState } from 'react';
import { Layout, Typography, Input, Button, Card, Tag, Space, message } from 'antd';
import { predictLabel } from './services/api';

// 🟢 1. IMPORT DU NOUVEAU COMPOSANT DE CONNEXION
import Login from './Login'; 

const { Header, Content } = Layout;
const { Title, Text } = Typography;
const { TextArea } = Input;

function App() {
  // 🟢 2. NOUVEAU STATE POUR GÉRER L'AUTHENTIFICATION
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const [text, setText] = useState('');
  const [labels, setLabels] = useState('joie, colère, tristesse, neutre');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // 🟢 3. FONCTION DE DÉCONNEXION (Maintenant à l'intérieur de App)
  const handleLogout = () => {
    localStorage.removeItem('userToken'); 
    setIsAuthenticated(false);
  };

  const handlePredict = async () => {
    if (!text.trim()) {
      message.warning('Veuillez entrer un texte à analyser.');
      return;
    }
    
    setLoading(true);
    
    try {
      const candidateLabels = labels.split(',').map(label => label.trim());
      const data = await predictLabel(text, candidateLabels);
      setResult(data);
      message.success('Analyse terminée avec succès !');
    } catch (error) {
      message.error('Erreur de communication avec l\'API. Vérifie que ton backend tourne.');
    } finally {
      setLoading(false);
    }
  };

  // 🟢 4. LOGIQUE D'AFFICHAGE (ROUTAGE SIMPLE)
  // Si l'utilisateur n'est pas connecté, on bloque l'accès et on affiche la page Login
  if (!isAuthenticated) {
    return <Login onLogin={() => setIsAuthenticated(true)} />;
  }

  // 🟢 5. SI CONNECTÉ : AFFICHAGE DE L'APPLICATION (Ton code original légèrement modifié)
  return (
    <Layout style={{ minHeight: '100vh', backgroundColor: '#f0f2f5' }}>
      
      {/* 🟢 Ajout de "justifyContent: 'space-between'" pour espacer le titre et le bouton */}
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          SmartLabel-Mini 🧠
        </Title>

        {/* 🟢 Ajout du bouton de déconnexion ici */}
        <button 
          onClick={handleLogout} 
          style={{ background: 'transparent', border: 'none', color: 'white', cursor: 'pointer', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <i className="fas fa-sign-out-alt"></i> Quitter
        </button>
      </Header>
      
      <Content style={{ padding: '50px', maxWidth: '800px', margin: '0 auto', width: '100%' }}>
        <Card 
          title="Outil de Labellisation Zero-Shot" 
          bordered={false}
          style={{ boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            
            <div>
              <Text strong>Texte à analyser :</Text>
              <TextArea
                rows={4}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Ex: Le client est vraiment furieux à cause du retard de livraison."
                style={{ marginTop: '8px' }}
              />
            </div>

            <div>
              <Text strong>Labels candidats (séparés par des virgules) :</Text>
              <Input
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                style={{ marginTop: '8px' }}
              />
            </div>

            <Button 
              type="primary" 
              size="large" 
              onClick={handlePredict} 
              loading={loading} 
              block
            >
              Soumettre à l'IA
            </Button>

            {result && (
              <Card 
                type="inner" 
                title="Résultat de la prédiction" 
                style={{ marginTop: 10, backgroundColor: '#f6ffed', borderColor: '#b7eb8f' }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div>
                    <Text strong>Label retenu : </Text> 
                    <Tag color="success" style={{ fontSize: '14px', padding: '4px 8px' }}>
                      {result.predicted_label.toUpperCase()}
                    </Tag>
                  </div>
                  <div>
                    <Text strong>Niveau de confiance : </Text> 
                    <Text>{(result.confidence_score * 100).toFixed(2)} %</Text>
                  </div>
                </div>
              </Card>
            )}
            
          </Space>
        </Card>
      </Content>
    </Layout>
  );
}

export default App;
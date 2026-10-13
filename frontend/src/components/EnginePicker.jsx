import { Alert, Radio, Space, Tag, Typography } from 'antd';
import { CloudOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

const { Text } = Typography;

// Explique pourquoi un moteur n'est pas proposé, pour que la personne sache quoi faire
const unavailableReason = (engine) => {
  if (engine.name === 'trained') {
    return "Aucun modèle entraîné pour exactement ces catégories. Entraînez-en un avec « python -m tools.train » (voir le README).";
  }
  if (engine.name === 'mistral') {
    return 'Non configuré : ajoutez MISTRAL_API_KEY dans backend/.env, puis redémarrez le backend.';
  }
  return 'Indisponible.';
};

const detail = (engine) => {
  if (engine.name === 'trained' && engine.available) {
    const model = (engine.models ?? []).find((m) => m.categories.length > 0);
    return model?.cv_accuracy != null ? `${(model.cv_accuracy * 100).toFixed(0)} % en validation croisée` : null;
  }
  return null;
};

// Choix du moteur de classification : local (par défaut), entraîné sur vos tickets, ou Mistral (cloud)
export default function EnginePicker({ engines, value, onChange }) {
  if (!engines.length) return null;
  const selected = engines.find((e) => e.name === value);

  return (
    <Space orientation="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
      <Text strong>Moteur de classification :</Text>
      <Radio.Group value={value} onChange={(e) => onChange(e.target.value)} style={{ width: '100%' }}>
        <Space orientation="vertical" size={6} style={{ width: '100%' }}>
          {engines.map((engine) => (
            <div key={engine.name}>
              <Radio value={engine.name} disabled={!engine.available}>
                {engine.label}{' '}
                {engine.sends_data_outside ? (
                  <Tag icon={<CloudOutlined />} color="orange">les textes quittent votre machine</Tag>
                ) : (
                  <Tag icon={<SafetyCertificateOutlined />} color="green">local</Tag>
                )}
                {detail(engine) && <Text type="secondary">{detail(engine)}</Text>}
              </Radio>
              {!engine.available && (
                <div><Text type="secondary" style={{ fontSize: 12, marginLeft: 24 }}>{unavailableReason(engine)}</Text></div>
              )}
            </div>
          ))}
        </Space>
      </Radio.Group>
      {selected?.sends_data_outside && (
        <Alert
          type="warning"
          showIcon
          title="Les tickets seront envoyés à un service externe (Mistral)."
          description="Les emails, numéros de téléphone, IBAN, numéros de carte et liens sont masqués avant l'envoi, mais pas les noms ni les adresses. Vérifiez que cet usage est autorisé pour vos données."
        />
      )}
    </Space>
  );
}

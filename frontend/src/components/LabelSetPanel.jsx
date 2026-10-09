import { useState } from 'react';
import { Button, Input, Popconfirm, Select, Space, Typography } from 'antd';

const { Text } = Typography;

// Choix et édition des catégories / priorités, avec jeux enregistrés pour l'équipe
export default function LabelSetPanel({ sets, current, onSelect, categories, priorities, onChange, onSave, onDelete, saving }) {
  const [newName, setNewName] = useState('');

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Text strong>Jeu de catégories :</Text>
        <Space.Compact style={{ width: '100%', marginTop: 8 }}>
          <Select
            style={{ flex: 1 }}
            placeholder="Choisir un jeu enregistré"
            value={current}
            onChange={onSelect}
            options={Object.keys(sets).map((name) => ({ value: name, label: name }))}
          />
          <Popconfirm title="Supprimer ce jeu pour toute l'équipe ?" okText="Supprimer" cancelText="Annuler" onConfirm={onDelete} disabled={!current}>
            <Button danger disabled={!current}>Supprimer</Button>
          </Popconfirm>
        </Space.Compact>
      </div>

      <div>
        <Text strong>Catégories (au moins 2) :</Text>
        <Select
          mode="tags"
          style={{ width: '100%', marginTop: 8 }}
          value={categories}
          onChange={onChange.categories}
          tokenSeparators={[',']}
          placeholder="Tapez une catégorie puis Entrée"
        />
      </div>

      <div>
        <Text strong>Priorités (facultatif, au moins 2) :</Text>
        <Select
          mode="tags"
          style={{ width: '100%', marginTop: 8 }}
          value={priorities}
          onChange={onChange.priorities}
          tokenSeparators={[',']}
          placeholder="Ex : urgente, normale, basse"
        />
      </div>

      <Space.Compact style={{ width: '100%' }}>
        <Input
          placeholder={current ? `Nom du jeu (vide : met à jour « ${current} »)` : 'Nom du jeu à enregistrer'}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          maxLength={60}
        />
        <Button
          loading={saving}
          disabled={!(newName.trim() || current) || categories.length < 2}
          onClick={() => onSave(newName.trim() || current).then(() => setNewName(''))}
        >
          Enregistrer pour l&apos;équipe
        </Button>
      </Space.Compact>
    </Space>
  );
}

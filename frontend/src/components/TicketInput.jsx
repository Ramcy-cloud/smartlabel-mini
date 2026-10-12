import { useState } from 'react';
import { Button, Input, Space, Tabs, Typography, Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import { MAX_TICKETS, parseTicketsCsv, parseTicketsText } from '../csv';

const { TextArea } = Input;
const { Text } = Typography;

const MAX_FILE_BYTES = 2 * 1024 * 1024;
const PLACEHOLDER = 'Un ticket par ligne, par exemple :\nMa facture du mois dernier est fausse\nLe colis est introuvable depuis une semaine';

// Saisie des tickets : fichier CSV ou texte collé (un par ligne)
export default function TicketInput({ onLoad }) {
  const [pasted, setPasted] = useState('');

  const load = (tickets) => {
    if (!tickets.length) {
      message.warning('Aucun ticket trouvé.');
      return;
    }
    if (tickets.length > MAX_TICKETS) {
      message.warning(`Maximum ${MAX_TICKETS} tickets à la fois : seuls les ${MAX_TICKETS} premiers sont chargés.`);
    }
    onLoad(tickets.slice(0, MAX_TICKETS));
  };

  const readFile = async (file) => {
    if (file.size > MAX_FILE_BYTES) {
      message.error('Fichier trop volumineux (2 Mo maximum).');
      return false;
    }
    try {
      load(parseTicketsCsv(await file.text()));
    } catch {
      message.error('Fichier illisible.');
    }
    return false; // pas d'envoi automatique : le fichier est lu dans le navigateur
  };

  return (
    <Tabs
      items={[
        {
          key: 'csv',
          label: 'Importer un CSV',
          children: (
            <Upload.Dragger accept=".csv,text/csv" showUploadList={false} beforeUpload={readFile} multiple={false}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p>Glissez un fichier CSV ici ou cliquez pour le choisir</p>
              <Text type="secondary">
                Colonne du texte : « texte », « message », « description »… (sinon la première). Colonnes facultatives : « id », « vip » (oui/non) et « anciennete_jours » (nombre de jours d'attente).
              </Text>
            </Upload.Dragger>
          ),
        },
        {
          key: 'paste',
          label: 'Coller des tickets',
          children: (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <TextArea rows={6} value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder={PLACEHOLDER} />
              <Button type="primary" disabled={!pasted.trim()} onClick={() => load(parseTicketsText(pasted))}>
                Charger les tickets
              </Button>
            </Space>
          ),
        },
      ]}
    />
  );
}

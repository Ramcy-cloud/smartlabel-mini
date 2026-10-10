import { Button, Select, Space, Table, Tag, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { rowStatus } from '../triage';

const STATUS_COLOR = { 'validé': 'success', 'corrigé': 'processing', 'à relire': 'warning', 'sûr': 'default' };

// Tableau des tickets classés : catégorie et priorité modifiables, validation ligne par ligne
export default function ResultsTable({ rows, threshold, categories, priorities, onUpdate }) {
  const topPriority = priorities[0];
  const columns = [
    { title: 'Id', dataIndex: 'id', width: 70 },
    {
      title: 'Ticket',
      dataIndex: 'text',
      render: (text) => (
        <Tooltip title={text} placement="topLeft">
          <div style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{text}</div>
        </Tooltip>
      ),
    },
    {
      title: 'Catégorie',
      dataIndex: 'category',
      width: 190,
      render: (value, row) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={value}
          options={categories.map((c) => ({ value: c, label: c }))}
          onChange={(v) => onUpdate(row.key, { category: v, validated: true })}
        />
      ),
    },
    {
      title: 'Confiance',
      dataIndex: 'category_confidence',
      width: 120,
      sorter: (a, b) => a.category_confidence - b.category_confidence,
      render: (v) => `${(v * 100).toFixed(0)} %`,
    },
    ...(priorities.length
      ? [{
          title: 'Priorité',
          dataIndex: 'priority',
          width: 170,
          render: (value, row) => {
            const manual = row.priority !== row.suggestedPriority;
            const why = manual ? 'Modifiée à la main' : (row.priority_reasons ?? []).join(' · ');
            return (
              <Space size={4}>
                <Select
                  size="small"
                  style={{ width: 120 }}
                  value={value}
                  options={priorities.map((p) => ({ value: p, label: p }))}
                  onChange={(v) => onUpdate(row.key, { priority: v, validated: true })}
                />
                <Tooltip title={why || 'Aucune raison enregistrée'}>
                  <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                </Tooltip>
              </Space>
            );
          },
        }]
      : []),
    {
      title: 'Statut',
      width: 110,
      render: (_, row) => {
        const status = rowStatus(row, threshold, topPriority);
        return <Tag color={STATUS_COLOR[status]}>{status}</Tag>;
      },
    },
    {
      title: '',
      width: 100,
      render: (_, row) =>
        row.validated ? (
          <Button size="small" onClick={() => onUpdate(row.key, { validated: false, category: row.suggestedCategory, priority: row.suggestedPriority })}>
            Annuler
          </Button>
        ) : (
          <Button size="small" type="primary" onClick={() => onUpdate(row.key, { validated: true })}>
            Valider
          </Button>
        ),
    },
  ];

  return (
    <Table
      rowKey="key"
      size="small"
      columns={columns}
      dataSource={rows}
      pagination={{ pageSize: 20, hideOnSinglePage: true }}
      scroll={{ x: 'max-content' }}
    />
  );
}

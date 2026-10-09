import { Button, Select, Table, Tag, Tooltip } from 'antd';
import { rowStatus } from '../triage';

const STATUS_COLOR = { 'validé': 'success', 'corrigé': 'processing', 'à relire': 'warning', 'sûr': 'default' };

// Tableau des tickets classés : catégorie et priorité modifiables, validation ligne par ligne
export default function ResultsTable({ rows, threshold, categories, priorities, onUpdate }) {
  const columns = [
    { title: 'Id', dataIndex: 'id', width: 70 },
    {
      title: 'Ticket',
      dataIndex: 'text',
      render: (text) => (
        <Tooltip title={text} placement="topLeft">
          <div style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{text}</div>
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
      render: (v, row) => {
        const pct = (x) => `${(x * 100).toFixed(0)} %`;
        return row.priority_confidence != null ? `${pct(v)} / ${pct(row.priority_confidence)}` : pct(v);
      },
    },
    ...(priorities.length
      ? [{
          title: 'Priorité',
          dataIndex: 'priority',
          width: 130,
          render: (value, row) => (
            <Select
              size="small"
              style={{ width: '100%' }}
              value={value}
              options={priorities.map((p) => ({ value: p, label: p }))}
              onChange={(v) => onUpdate(row.key, { priority: v, validated: true })}
            />
          ),
        }]
      : []),
    {
      title: 'Statut',
      width: 110,
      render: (_, row) => {
        const status = rowStatus(row, threshold);
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

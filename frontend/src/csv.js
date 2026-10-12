import Papa from 'papaparse';

const TEXT_COLUMNS = ['text', 'texte', 'message', 'description', 'ticket', 'contenu', 'body', 'objet'];
const ID_COLUMNS = ['id', 'numéro', 'numero', 'référence', 'reference', 'ticket_id'];

const VIP_COLUMNS = ['vip', 'client_vip', 'prioritaire'];
const AGE_COLUMNS = ['anciennete_jours', 'ancienneté_jours', 'age_jours', 'anciennete', 'ancienneté', 'age'];
const TRUE_VALUES = ['1', 'oui', 'o', 'yes', 'y', 'true', 'vrai', 'x'];

export const MAX_TICKETS = 500;

// Lit un CSV de tickets : colonne de texte repérée par son nom (sinon la première), colonne d'identifiant facultative
export function parseTicketsCsv(content) {
  const { data, meta } = Papa.parse(content.replace(/^\uFEFF/, ''), { header: true, skipEmptyLines: true });
  const fields = meta.fields ?? [];
  const find = (names) => fields.find((f) => names.includes(f.trim().toLowerCase()));
  const textField = find(TEXT_COLUMNS) ?? fields[0];
  const idField = find(ID_COLUMNS);
  const vipField = find(VIP_COLUMNS);
  const ageField = find(AGE_COLUMNS);
  if (!textField) return [];
  return data
    .map((row, index) => ({
      id: idField && row[idField] ? String(row[idField]).trim() : String(index + 1),
      text: String(row[textField] ?? '').trim(),
      vip: vipField ? TRUE_VALUES.includes(String(row[vipField] ?? '').trim().toLowerCase()) : false,
      age_days: ageField && /^\d{1,5}$/.test(String(row[ageField] ?? '').trim()) ? Number(row[ageField]) : null,
    }))
    .filter((t) => t.text);
}

// Un texte collé : un ticket par ligne
export function parseTicketsText(content) {
  return content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((text, index) => ({ id: String(index + 1), text, vip: false, age_days: null }));
}

// Neutralise les formules (=, +, -, @) pour que l'export ne soit pas exécuté par Excel
const safeCell = (value) => (typeof value === 'string' && /^[=+\-@\t\r]/.test(value) ? `'${value}` : value);

export function toCsv(rows) {
  const safe = rows.map((row) => Object.fromEntries(Object.entries(row).map(([k, v]) => [k, safeCell(v)])));
  return '\uFEFF' + Papa.unparse(safe, { delimiter: ';' });
}

export function downloadCsv(filename, content) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

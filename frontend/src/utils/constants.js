/**
 * Severity and category display constants.
 * Centralized here so every component uses the same labels and mappings.
 */

export const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 };

export const SEVERITY_LABELS = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

export const CATEGORY_LABELS = {
  bug: 'Bug',
  security: 'Security',
  style: 'Style',
  performance: 'Performance',
};

export const LANGUAGES = [
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'java', label: 'Java' },
  { value: 'cpp', label: 'C++' },
];

/**
 * Map language values to Monaco Editor language identifiers.
 * Monaco uses slightly different names for some languages.
 */
export const MONACO_LANGUAGE_MAP = {
  python: 'python',
  javascript: 'javascript',
  java: 'java',
  cpp: 'cpp',
};

/**
 * Status labels and their corresponding badge classes.
 */
export const STATUS_CONFIG = {
  pending: { label: 'Pending', badgeClass: 'badge--info' },
  processing: { label: 'Processing', badgeClass: 'badge--warning' },
  complete: { label: 'Complete', badgeClass: 'badge--success' },
  failed: { label: 'Failed', badgeClass: 'badge--critical' },
};

/**
 * Chart colors that match our design system severity/category colors.
 */
export const CHART_COLORS = {
  critical: '#f85149',
  warning: '#d29922',
  info: '#58a6ff',
  security: '#f85149',
  bug: '#d29922',
  style: '#58a6ff',
  performance: '#bc8cff',
};

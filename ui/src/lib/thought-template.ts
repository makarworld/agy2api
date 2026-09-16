const MARKER = '{...}';

const escapeNewlines = (value: string) => value.replaceAll('\n', '\\n');
const restoreNewlines = (value: string) => value.replaceAll('\\n', '\n');

export function buildThoughtTemplate(prefix: string, suffix: string): string {
  return `${escapeNewlines(prefix)}${MARKER}${escapeNewlines(suffix)}`;
}

export function parseThoughtTemplate(template: string): { prefix: string; suffix: string } | null {
  const first = template.indexOf(MARKER);
  if (first < 0 || first !== template.lastIndexOf(MARKER)) return null;
  return {
    prefix: restoreNewlines(template.slice(0, first)),
    suffix: restoreNewlines(template.slice(first + MARKER.length)),
  };
}

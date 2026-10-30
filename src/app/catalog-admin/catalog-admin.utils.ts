import { HttpErrorResponse } from '@angular/common/http';
import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';
import { TranslateService } from '@ngx-translate/core';
import { ToolGroup } from '../data/models/catalog.model';

/** A readable message for a failed request (FastAPI puts it in `detail`). */
export function describeHttpError(error: unknown, translate?: TranslateService): string {
  if (error instanceof HttpErrorResponse) {
    const detail = error.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: any) => (d?.loc ? `${d.loc.slice(1).join('.')}: ` : '') + (d?.msg ?? JSON.stringify(d)))
        .join('; ');
    }
    if (typeof error.error?.error === 'string') return error.error.error;
    if (error.status === 0) {
      return translate ? translate.instant('catalog.admin.unreachable') : 'The server could not be reached.';
    }
    return `${error.status} ${error.statusText}`.trim();
  }
  return error instanceof Error ? error.message : String(error);
}

/** Trimmed text, or null when empty (for optional fields). */
export function textOrNull(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text.length > 0 ? text : null;
}

/** A number, or null when the field is empty. */
export function numberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Parse a JSON object field; empty text gives null. Throws on invalid JSON. */
export function parseJsonObject<T = Record<string, unknown>>(text: unknown): T | null {
  const trimmed = textOrNull(text);
  if (!trimmed) return null;
  return JSON.parse(trimmed) as T;
}

/** Pretty JSON for a textarea; empty for null. */
export function formatJson(value: unknown): string {
  if (value === null || value === undefined) return '';
  return JSON.stringify(value, null, 2);
}

/**
 * Validates a textarea that holds a JSON object (or is empty).
 * With `stringValues`, every value must be a string (HTTP headers).
 */
export function jsonObjectValidator(stringValues = false): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const text = textOrNull(control.value);
    if (!text) return null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return { json: true };
    }
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { jsonObject: true };
    }
    if (stringValues && Object.values(parsed as Record<string, unknown>).some(v => typeof v !== 'string')) {
      return { jsonStringValues: true };
    }
    return null;
  };
}

/** {{placeholders}} used in a persona prompt. */
export function findPlaceholders(prompt: string): string[] {
  const names = new Set<string>();
  for (const match of prompt.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g)) {
    names.add(match[1]);
  }
  return [...names];
}

const TOOL_ICONS: Record<ToolGroup, string> = {
  files: 'folder_open',
  web_search: 'travel_explore',
  knowledge_graph: 'hub'
};

/** Material icon of a tool group (its label is the translation catalog.tools.<id>). */
export function toolIcon(id: ToolGroup): string {
  return TOOL_ICONS[id] ?? 'build';
}

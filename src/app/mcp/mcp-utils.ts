import { AbstractControl, FormControl, FormGroup, ValidationErrors, ValidatorFn, Validators } from '@angular/forms';
import { IMcpServerOut, MCP_SECRET_VAR_SUFFIXES } from '../data/models/mcp.model';

/** A key/value row of the server dialog (headers, stdio environment). */
export type KeyValueRow = FormGroup<{
  key: FormControl<string>;
  value: FormControl<string>;
  /** Users' headers: the name of a header the server stores (its value is never sent back), else null. */
  stored: FormControl<string | null>;
}>;

/** HTTP header names (RFC 9110 token characters). */
export const HEADER_NAME_PATTERN = /^[A-Za-z0-9!#$%&'*+.^_`|~-]+$/;
/** Environment variable names. */
export const ENV_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

const VAR_REFERENCE = /\$\{([^}]*)\}/g;

/** The names in ${VAR} references that the server won't fill in (they must end in _KEY, _TOKEN, _SECRET or _API). */
export function invalidSecretVars(text: string | null | undefined): string[] {
  if (!text) return [];
  const invalid = new Set<string>();
  for (const match of text.matchAll(VAR_REFERENCE)) {
    const name = match[1].trim();
    if (!ENV_NAME_PATTERN.test(name) || !MCP_SECRET_VAR_SUFFIXES.some(suffix => name.toUpperCase().endsWith(suffix))) {
      invalid.add(name || '${}');
    }
  }
  return [...invalid];
}

/** Admin servers: ${VAR} references must name variables the server may send (docs/mcp.md). */
export function secretVarsValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const names = invalidSecretVars(control.value);
    return names.length > 0 ? { secretVar: { names: names.join(', ') } } : null;
  };
}

/** The variable names of a field's secretVar error, or null when it has none. */
export function secretVarNames(control: AbstractControl): string | null {
  const error = control.getError('secretVar') as { names: string } | null;
  return error ? error.names : null;
}

/** The variable with an admin server's OAuth client secret must end in one of these (docs/mcp.md). */
const CLIENT_SECRET_VAR_SUFFIXES = ['_KEY', '_TOKEN', '_SECRET'];

/** The name of the environment variable with the OAuth client secret of an admin server. */
export function secretVarNameValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const name = String(control.value ?? '').trim();
    if (!name) return null;
    return ENV_NAME_PATTERN.test(name) && CLIENT_SECRET_VAR_SUFFIXES.some(suffix => name.toUpperCase().endsWith(suffix))
      ? null
      : { secretEnv: true };
  };
}

/**
 * An http(s) address. Admin servers may use ${VAR} anywhere in it, also for the whole address,
 * so only an address without a variable at its start must begin with http:// or https://.
 */
export function urlValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const url = String(control.value ?? '').trim();
    if (!url || url.startsWith('${')) return null;
    return /^https?:\/\/\S+$/i.test(url) ? null : { url: true };
  };
}

/** Required only while the condition holds (e.g. the URL for HTTP servers, the command for stdio). */
export function requiredWhen(condition: () => boolean): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null =>
    condition() ? Validators.required(control) : null;
}

/** A row's value is required, except for a stored header whose name is unchanged (empty keeps the stored value). */
export function keyValueRowValidator(): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const key = group.get('key')?.value as string;
    const value = group.get('value');
    const stored = group.get('stored')?.value as string | null;
    const keepsStored = stored !== null && key.trim() === stored;
    const missing = !keepsStored && !String(value?.value ?? '').length;
    // The error sits on the value field, so the field shows it
    if (value) {
      const errors = { ...(value.errors ?? {}) };
      if (missing) errors['required'] = true;
      else delete errors['required'];
      value.setErrors(Object.keys(errors).length > 0 ? errors : null, { emitEvent: false });
    }
    return null;
  };
}

/** The rows as an object; empty keys are left out. Empty values stay (a stored header keeps its value). */
export function rowsToRecord(rows: KeyValueRow[]): Record<string, string> {
  const record: Record<string, string> = {};
  for (const row of rows) {
    const key = row.controls.key.value.trim();
    if (key) record[key] = row.controls.value.value;
  }
  return record;
}

/** Keys that occur in more than one row. */
export function duplicateKeys(rows: KeyValueRow[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const row of rows) {
    const key = row.controls.key.value.trim().toLowerCase();
    if (!key) continue;
    if (seen.has(key)) duplicates.add(row.controls.key.value.trim());
    seen.add(key);
  }
  return [...duplicates];
}

/** Where the server is: its URL, or its command line (stdio). */
export function serverEndpoint(server: IMcpServerOut): string {
  if (server.transport === 'stdio') {
    return [server.command ?? '', ...(server.args ?? [])].filter(part => part.length > 0)
      .map(part => (/\s/.test(part) ? `"${part}"` : part)).join(' ');
  }
  return server.url ?? '';
}

/** The servers in their order: sort order, then name. */
export function sortServers(servers: IMcpServerOut[]): IMcpServerOut[] {
  return [...servers].sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name));
}

/** Translation key of a server's tool selection: all tools, none, or a count. */
export function toolSelectionKey(server: IMcpServerOut): string {
  if (server.tools == null) return 'mcp.toolsAll';
  return server.tools.length === 0 ? 'mcp.toolsNone' : 'mcp.toolsCount';
}

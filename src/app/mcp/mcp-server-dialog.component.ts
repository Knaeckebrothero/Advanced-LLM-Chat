import { Component, ElementRef, Inject, Injector } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormArray, FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';
import {
  IMcpConfig,
  IMcpServerCreate,
  IMcpServerOut,
  IMcpServerUpdate,
  McpAuth,
  McpTransport,
  MCP_SLUG_PATTERN
} from '../data/models/mcp.model';
import {
  describeHttpError,
  DIALOG_ERROR,
  INVALID_FIELD,
  numberOrNull,
  revealInDialog,
  textOrNull
} from '../catalog-admin/catalog-admin.utils';
import { McpKeyValueRowsComponent } from './mcp-key-value-rows.component';
import {
  duplicateKeys,
  ENV_NAME_PATTERN,
  HEADER_NAME_PATTERN,
  KeyValueRow,
  keyValueRowValidator,
  rowsToRecord,
  secretVarNames,
  secretVarNameValidator,
  secretVarsValidator,
  urlValidator
} from './mcp-utils';

export interface McpServerDialogData {
  server: IMcpServerOut | null;  // null = add a new server
  /** An admin server (the agents', on the Agents page), else the user's own (MCP servers page). */
  admin: boolean;
  config: IMcpConfig | null;  // null: not known, nothing is switched off then
  /** Creates (id null) or updates the server; the dialog closes with what it returns. */
  save: (id: number | null, body: IMcpServerCreate | IMcpServerUpdate) => Promise<IMcpServerOut>;
}

/** Opens the dialog in the style of the Agents page's dialogs; closes with the saved server. */
export function openMcpServerDialog(dialog: MatDialog, injector: Injector, data: McpServerDialogData): Promise<IMcpServerOut | undefined> {
  const ref = dialog.open<McpServerDialogComponent, McpServerDialogData, IMcpServerOut>(McpServerDialogComponent, {
    data,
    injector,
    panelClass: 'catalog-dialog-panel',
    backdropClass: 'custom-backdrop',
    maxWidth: '95vw',
    autoFocus: 'first-tabbable'
  });
  return firstValueFrom(ref.afterClosed());
}

/**
 * Add or edit an MCP server: where it is (an HTTP address, or for admins a command the backend
 * starts), how it signs in (headers or OAuth) and who may use it. Admin servers keep secrets in
 * environment variables (${VAR}); users' header values are secrets the server never sends back,
 * so an empty value keeps the stored one. The tool selection is edited in the test result.
 */
@Component({
  selector: 'app-mcp-server-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatRadioModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule,
    McpKeyValueRowsComponent
  ],
  templateUrl: './mcp-server-dialog.component.html',
  styleUrls: ['../catalog-admin/catalog-dialog.scss', './mcp-server-dialog.component.scss']
})
export class McpServerDialogComponent {
  readonly server: IMcpServerOut | null;
  readonly admin: boolean;
  readonly config: IMcpConfig | null;
  readonly transports: McpTransport[];
  readonly authModes: McpAuth[] = ['none', 'headers', 'oauth'];
  readonly envValuePlaceholder = '${GITHUB_TOKEN}';
  readonly secretVarNames = secretVarNames;
  readonly headerValuePlaceholder: string;

  readonly args: FormArray<FormControl<string>>;
  readonly env: FormArray<KeyValueRow>;
  readonly headers: FormArray<KeyValueRow>;
  readonly form;

  saving = false;
  error: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) private data: McpServerDialogData,
    private dialogRef: MatDialogRef<McpServerDialogComponent, IMcpServerOut>,
    private host: ElementRef<HTMLElement>,
    private translate: TranslateService,
    private fb: FormBuilder
  ) {
    const s = data.server;
    this.server = s;
    this.admin = data.admin;
    this.config = data.config;
    this.transports = data.admin ? ['http', 'sse', 'stdio'] : ['http', 'sse'];
    this.headerValuePlaceholder = data.admin ? 'Bearer ${GITHUB_TOKEN}' : 'Bearer …';
    const secretVars = data.admin ? [secretVarsValidator()] : [];

    this.args = fb.nonNullable.array((s?.args ?? []).map(arg => fb.nonNullable.control(arg)));
    this.env = fb.array(Object.entries(s?.env ?? {}).map(([key, value]) => this.row(key, value, null, true)));
    // Admin servers return their headers as written; users' servers only the names (the values stay on the server)
    const headerRows = data.admin
      ? Object.entries(s?.headers ?? {}).map(([key, value]) => this.row(key, value, null, false))
      : (s?.headerNames ?? []).map(name => this.row(name, '', name, false));
    this.headers = fb.array(headerRows);

    this.form = fb.nonNullable.group({
      name: [s?.name ?? '', Validators.required],
      slug: [{ value: s?.slug ?? '', disabled: s !== null }, Validators.pattern(MCP_SLUG_PATTERN)],
      description: [s?.description ?? ''],
      transport: [(s?.transport ?? 'http') as McpTransport],
      url: [s?.url ?? '', [Validators.required, urlValidator(), ...secretVars]],
      command: [s?.command ?? '', Validators.required],
      args: this.args,
      env: this.env,
      auth: [(s?.auth ?? 'none') as McpAuth],
      headers: this.headers,
      oauthClientId: [s?.oauthClientId ?? ''],
      oauthClientSecretEnv: [s?.oauthClientSecretEnv ?? '', secretVarNameValidator()],
      oauthScopes: [s?.oauthScopes ?? ''],
      availableToGuests: [s?.availableToGuests ?? false],
      enabled: [s?.enabled ?? true],
      sortOrder: [s?.sortOrder ?? 0]
    });

    // Only the fields of the chosen transport and sign-in count (and are validated)
    this.syncEnabled();
    this.form.controls.transport.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.syncEnabled());
    this.form.controls.auth.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.syncEnabled());
  }

  get isNew(): boolean {
    return this.server === null;
  }

  get transport(): McpTransport {
    return this.form.controls.transport.value;
  }

  /** The sign-in that counts: a stdio server has none (OAuth and headers are HTTP only). */
  get auth(): McpAuth {
    return this.transport === 'stdio' ? 'none' : this.form.controls.auth.value;
  }

  /** stdio needs MCP_STDIO_ENABLED; a server that has it already keeps the option (it shows why it's unavailable). */
  isTransportDisabled(transport: McpTransport): boolean {
    return transport === 'stdio' && this.config?.stdio === false && this.server?.transport !== 'stdio';
  }

  /** Users' servers keep secrets encrypted: without ENCRYPTION_KEY, neither headers nor OAuth. */
  isAuthDisabled(auth: McpAuth): boolean {
    return !this.admin && auth !== 'none' && this.config?.encryption === false && this.server?.auth !== auth;
  }

  /** OAuth tokens are stored encrypted for everyone: admins may still define the server, it just won't work yet. */
  get oauthNeedsEncryption(): boolean {
    return this.config?.encryption === false && this.auth === 'oauth';
  }

  get stdioOff(): boolean {
    return this.config?.stdio === false;
  }

  private row(key: string, value: string, stored: string | null, env: boolean): KeyValueRow {
    const secretVars = this.data.admin ? [secretVarsValidator()] : [];
    return this.fb.nonNullable.group({
      key: [key, [Validators.required, Validators.pattern(env ? ENV_NAME_PATTERN : HEADER_NAME_PATTERN)]],
      value: [value, secretVars],
      stored: this.fb.control<string | null>(stored)
    }, { validators: keyValueRowValidator() }) as KeyValueRow;
  }

  addArg(): void {
    this.args.push(this.fb.nonNullable.control(''));
  }

  removeArg(index: number): void {
    this.args.removeAt(index);
    this.args.markAsDirty();
  }

  addEnv(): void {
    this.env.push(this.row('', '', null, true));
  }

  addHeader(): void {
    this.headers.push(this.row(this.headers.length === 0 ? 'Authorization' : '', '', null, false));
  }

  private syncEnabled(): void {
    const stdio = this.transport === 'stdio';
    const oauth = this.auth === 'oauth';
    const set = (control: AbstractControl, on: boolean) => {
      if (on && control.disabled) control.enable({ emitEvent: false });
      if (!on && control.enabled) control.disable({ emitEvent: false });
    };
    const c = this.form.controls;
    set(c.url, !stdio);
    set(c.command, stdio);
    set(this.args, stdio);
    set(this.env, stdio);
    set(this.headers, this.auth === 'headers');
    set(c.oauthClientId, oauth);
    set(c.oauthClientSecretEnv, oauth && this.admin);
    set(c.oauthScopes, oauth);
  }

  async save(): Promise<void> {
    if (this.saving) return;
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      revealInDialog(this.host.nativeElement, INVALID_FIELD);
      return;
    }
    const v = this.form.getRawValue();
    const stdio = v.transport === 'stdio';
    const auth = this.auth;
    const headers = auth === 'headers';
    const oauth = auth === 'oauth';

    const duplicates = [
      ...(stdio ? duplicateKeys(this.env.controls) : []),
      ...(headers ? duplicateKeys(this.headers.controls) : [])
    ];
    if (duplicates.length > 0) {
      this.error = this.translate.instant('mcp.dialog.duplicateKeys', { names: duplicates.join(', ') });
      revealInDialog(this.host.nativeElement, DIALOG_ERROR);
      return;
    }

    // Every field is sent (null clears an optional one), except the tool selection, which the test edits
    const body: IMcpServerCreate = {
      name: v.name.trim(),
      description: textOrNull(v.description),
      transport: v.transport,
      url: stdio ? null : textOrNull(v.url),
      command: stdio ? textOrNull(v.command) : null,
      args: stdio ? v.args.map(arg => arg.trim()).filter(arg => arg.length > 0) : [],
      env: stdio ? rowsToRecord(this.env.controls) : {},
      auth,
      headers: headers ? rowsToRecord(this.headers.controls) : null,
      oauthClientId: oauth ? textOrNull(v.oauthClientId) : null,
      oauthScopes: oauth ? textOrNull(v.oauthScopes) : null,
      enabled: !!v.enabled
    };
    if (this.admin) {
      body.oauthClientSecretEnv = oauth ? textOrNull(v.oauthClientSecretEnv) : null;
      body.availableToGuests = !!v.availableToGuests;
      body.sortOrder = numberOrNull(v.sortOrder) ?? 0;
    }
    const slug = textOrNull(v.slug);
    if (this.isNew && slug) body.slug = slug;

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.data.save(this.server?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
      revealInDialog(this.host.nativeElement, DIALOG_ERROR);
    } finally {
      this.saving = false;
    }
  }
}

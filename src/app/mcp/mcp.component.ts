import { Component, DestroyRef, Injector, OnInit, computed, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS, MatFormFieldDefaultOptions } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleChange, MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../services/api.service';
import { AuthService } from '../auth/auth.service';
import { IMcpConfig, IMcpServerCreate, IMcpServerOut, IMcpServerUpdate, IMcpTestResult } from '../data/models/mcp.model';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { confirmDialog } from '../knowledge-base/kb-confirm';
import { McpServerDialogData, openMcpServerDialog } from './mcp-server-dialog.component';
import { McpTestResultComponent } from './mcp-test-result.component';
import { sortServers, toolSelectionKey } from './mcp-utils';

type PageState = 'loading' | 'ready' | 'forbidden' | 'error';

/** Codes of a failed OAuth sign-in (?error=<code>) that have their own message; others show as they are. */
const SIGN_IN_ERRORS = ['expired', 'wrong_user', 'denied', 'failed'];

/** What is going on with a server's row: a test and its result, a sign-in or sign-out. */
interface ServerState {
  testing?: boolean;
  result?: IMcpTestResult;
  savingTools?: boolean;
  signingIn?: boolean;
  signingOut?: boolean;
}

/**
 * The MCP servers page (route /mcp, loaded on demand) for signed-in users: their own MCP servers,
 * which agents use only when they allow users' own servers (tool group user_mcp), and the agents'
 * servers with OAuth, where every user signs in with their own account. The OAuth callback comes
 * back here with ?connected=<id> or ?error=<reason>&server=<id>.
 */
@Component({
  selector: 'app-mcp',
  standalone: true,
  imports: [
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslateModule,
    McpTestResultComponent
  ],
  providers: [
    // The server dialog gets this page's injector: outlined fields whose hints may wrap
    {
      provide: MAT_FORM_FIELD_DEFAULT_OPTIONS,
      useValue: { appearance: 'outline', subscriptSizing: 'dynamic' } as MatFormFieldDefaultOptions
    }
  ],
  templateUrl: './mcp.component.html',
  styleUrls: ['../catalog-admin/catalog-admin-list.scss', './mcp-list.scss', './mcp.component.scss']
})
export class McpComponent implements OnInit {
  readonly toolSelectionKey = toolSelectionKey;

  readonly state = signal<PageState>('loading');
  readonly loadError = signal<string | null>(null);
  readonly config = signal<IMcpConfig | null>(null);
  readonly own = signal<IMcpServerOut[]>([]);
  readonly shared = signal<IMcpServerOut[]>([]);

  /** MCP is switched off on the server (MCP_ENABLED). */
  readonly mcpOff = computed(() => this.config()?.enabled === false);
  /** Users may not use their own servers (MCP off, or MCP_USER_SERVERS off). */
  readonly ownOff = computed(() => {
    const config = this.config();
    return !!config && (!config.enabled || !config.userServers);
  });
  /** No ENCRYPTION_KEY: no OAuth sign-in, no headers for users' servers. */
  readonly noEncryption = computed(() => this.config()?.encryption === false);

  states: Record<number, ServerState | undefined> = {};
  private loaded: Promise<void> = Promise.resolve();

  constructor(
    private api: ApiService,
    private route: ActivatedRoute,
    private router: Router,
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private injector: Injector,
    private destroyRef: DestroyRef,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    this.loaded = this.load();
    // Back from an OAuth sign-in: say how it went, then drop the parameters from the address
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(query => {
      const connected = query.get('connected');
      const error = query.get('error');
      if (connected !== null || error !== null) this.reportSignIn(connected, error, query.get('server'));
    });
  }

  async load(): Promise<void> {
    this.state.set('loading');
    this.loadError.set(null);
    try {
      this.config.set(await this.api.getMcpConfig());
    } catch (error) {
      if (isForbidden(error)) {
        this.state.set('forbidden');
        return;
      }
      this.config.set(null);  // The servers may still load; nothing is shown as switched off then
    }
    try {
      await this.loadServers();
      this.state.set('ready');
    } catch (error) {
      if (isForbidden(error)) {
        this.state.set('forbidden');
      } else if (error instanceof HttpErrorResponse && error.status === 503) {
        // Switched off on the server: the notices say so
        this.own.set([]);
        this.shared.set([]);
        this.state.set('ready');
      } else {
        this.loadError.set(describeHttpError(error, this.translate));
        this.state.set('error');
      }
    }
  }

  private async loadServers(): Promise<void> {
    const list = await this.api.getMcpServers();
    this.own.set(sortServers(list?.own ?? []));
    this.shared.set(sortServers(list?.shared ?? []));
  }

  /** Reload the lists after a change; a failure only shows a message. */
  private async refresh(): Promise<void> {
    try {
      await this.loadServers();
    } catch (error) {
      this.showError(error);
    }
  }

  private replace(server: IMcpServerOut): void {
    const update = (list: IMcpServerOut[]) => list.map(s => (s.id === server.id ? { ...s, ...server } : s));
    this.own.set(update(this.own()));
    this.shared.set(update(this.shared()));
  }

  private serverName(id: string | null): string | null {
    const numeric = Number(id);
    if (!id || !Number.isFinite(numeric)) return null;
    return [...this.own(), ...this.shared()].find(s => s.id === numeric)?.name ?? null;
  }

  /** The page has just loaded from the provider's redirect: the translations may still be on their way (get waits). */
  private async reportSignIn(connected: string | null, error: string | null, server: string | null): Promise<void> {
    await this.loaded;
    const t = (key: string, params?: Record<string, unknown>) => firstValueFrom(this.translate.get(key, params));
    if (error !== null) {
      const name = this.serverName(server ?? connected);
      const reason = SIGN_IN_ERRORS.includes(error) ? await t('mcp.signInError.' + error)
        : error || await t('catalog.admin.personas.toolUnavailableUnknown');
      this.snackBar.open(
        name ? await t('mcp.signInFailed', { name, reason }) : await t('mcp.signInFailedUnknown', { reason }),
        await t('catalog.common.close'), { duration: 10000 }
      );
    } else {
      const name = this.serverName(connected);
      this.snackBar.open(name ? await t('mcp.signedInTo', { name }) : await t('mcp.signedInDone'), undefined, { duration: 4000 });
    }
    this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
  }

  // What may be done

  /** Sign-in needs OAuth tokens stored encrypted; own servers also need users' servers switched on. */
  canSignIn(server: IMcpServerOut): boolean {
    return !this.mcpOff() && !this.noEncryption() && (server.shared || !this.ownOff());
  }

  stateOf(server: IMcpServerOut): ServerState {
    return this.states[server.id] ?? {};
  }

  // Your servers

  private dialogData(server: IMcpServerOut | null): McpServerDialogData {
    // Admins' own servers may use private addresses too (the backend only guards other users')
    const config = this.config();
    return {
      server,
      admin: false,
      config: config && this.auth.isAdmin ? { ...config, privateUrls: true } : config,
      save: (id: number | null, body: IMcpServerCreate | IMcpServerUpdate) => id === null
        ? this.api.createMcpServer(body as IMcpServerCreate)
        : this.api.updateMcpServer(id, body as IMcpServerUpdate)
    };
  }

  async add(): Promise<void> {
    const saved = await openMcpServerDialog(this.dialog, this.injector, this.dialogData(null));
    if (saved) await this.afterSave(saved);
  }

  async edit(server: IMcpServerOut): Promise<void> {
    const saved = await openMcpServerDialog(this.dialog, this.injector, this.dialogData(server));
    if (saved) {
      this.states[server.id] = undefined;  // The test was of the old settings
      await this.afterSave(saved);
    }
  }

  /** A server with OAuth that isn't signed in yet offers the sign-in right away. */
  private async afterSave(saved: IMcpServerOut): Promise<void> {
    await this.refresh();
    const message = this.translate.instant('mcp.own.saved', { name: saved.name });
    if (saved.auth === 'oauth' && !saved.connected && this.canSignIn(saved)) {
      this.snackBar.open(message, this.translate.instant('mcp.signIn'), { duration: 8000 })
        .onAction().subscribe(() => this.signIn(saved));
    } else {
      this.snackBar.open(message, undefined, { duration: 3000 });
    }
  }

  async setEnabled(server: IMcpServerOut, change: MatSlideToggleChange): Promise<void> {
    try {
      this.replace(await this.api.updateMcpServer(server.id, { enabled: change.checked }));
    } catch (error) {
      change.source.checked = !change.checked;  // Flip the switch back
      this.showError(error);
    }
  }

  async remove(server: IMcpServerOut): Promise<void> {
    const confirmed = await confirmDialog(this.dialog, {
      title: this.translate.instant('mcp.own.deleteTitle', { name: server.name }),
      message: this.translate.instant('mcp.own.deleteMessage'),
      confirmLabel: this.translate.instant('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.api.deleteMcpServer(server.id);
      this.states[server.id] = undefined;
      await this.refresh();
      this.snackBar.open(this.translate.instant('mcp.own.deleted', { name: server.name }), undefined, { duration: 3000 });
    } catch (error) {
      this.showError(error);
    }
  }

  // Test and tool selection

  async test(server: IMcpServerOut): Promise<void> {
    this.states[server.id] = { testing: true };
    try {
      const result = await this.api.testMcpServer(server.id);
      this.states[server.id] = { result };
    } catch (error) {
      this.states[server.id] = {
        result: { ok: false, authRequired: false, error: describeHttpError(error, this.translate), tools: [] }
      };
    }
  }

  closeTest(server: IMcpServerOut): void {
    this.states[server.id] = undefined;
  }

  async saveTools(server: IMcpServerOut, tools: string[] | null): Promise<void> {
    const state = this.states[server.id];
    if (state) state.savingTools = true;
    try {
      this.replace(await this.api.updateMcpServer(server.id, { tools }));
      this.snackBar.open(this.translate.instant('mcp.test.selectionSaved'), undefined, { duration: 3000 });
    } catch (error) {
      this.showError(error);
    } finally {
      if (state) state.savingTools = false;
    }
  }

  // OAuth sign-in

  /** The provider's sign-in page opens in this tab; it sends the browser back to this page. */
  async signIn(server: IMcpServerOut): Promise<void> {
    const state = this.states[server.id] ?? {};
    this.states[server.id] = { ...state, signingIn: true };
    try {
      const { authorizationUrl } = await this.api.connectMcpServer(server.id);
      window.location.href = authorizationUrl;
    } catch (error) {
      this.states[server.id] = { ...state, signingIn: false };
      this.showError(error);
    }
  }

  async signOut(server: IMcpServerOut): Promise<void> {
    this.states[server.id] = { ...(this.states[server.id] ?? {}), signingOut: true };
    try {
      await this.api.disconnectMcpServer(server.id);
      this.states[server.id] = undefined;
      this.replace({ ...server, connected: false });
      await this.refresh();
      this.snackBar.open(this.translate.instant('mcp.signedOutOf', { name: server.name }), undefined, { duration: 3000 });
    } catch (error) {
      this.states[server.id] = { ...(this.states[server.id] ?? {}), signingOut: false };
      this.showError(error);
    }
  }

  private showError(error: unknown): void {
    this.snackBar.open(this.translate.instant('mcp.failed', { error: describeHttpError(error, this.translate) }),
      this.translate.instant('catalog.common.close'), { duration: 8000 });
  }
}

function isForbidden(error: unknown): boolean {
  return error instanceof HttpErrorResponse && (error.status === 401 || error.status === 403);
}

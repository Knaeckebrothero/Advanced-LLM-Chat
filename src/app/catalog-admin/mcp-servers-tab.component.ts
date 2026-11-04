import { Component } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleChange, MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IMcpServerCreate, IMcpServerOut, IMcpServerUpdate, IMcpTestResult } from '../data/models/mcp.model';
import { McpServerDialogComponent, McpServerDialogData } from '../mcp/mcp-server-dialog.component';
import { McpTestResultComponent } from '../mcp/mcp-test-result.component';
import { serverEndpoint, sortServers, toolSelectionKey } from '../mcp/mcp-utils';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { describeHttpError } from './catalog-admin.utils';

interface TestState {
  running: boolean;
  result?: IMcpTestResult;
  savingTools?: boolean;
  signingIn?: boolean;
}

/**
 * The MCP servers of the agents: servers of the Model Context Protocol whose tools agents use
 * (each agent picks its servers in its dialog). Secrets come from the server's environment
 * (${VAR}). The test connects as the admin and lists the tools, where the selection offered to
 * the agents is edited.
 */
@Component({
  selector: 'app-mcp-servers-tab',
  standalone: true,
  imports: [
    AsyncPipe,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule,
    McpTestResultComponent
  ],
  template: `
    <div class="section-header">
      <div class="section-heading">
        <h2 class="section-title">{{ 'catalog.admin.mcp.title' | translate }}</h2>
        <p class="section-intro">{{ 'catalog.admin.mcp.intro' | translate }}</p>
      </div>
      <div class="section-actions">
        <button mat-flat-button color="primary" type="button" (click)="add()">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.mcp.add' | translate }}
        </button>
      </div>
    </div>

    @if (store.mcpConfig$ | async; as config) {
      @if (!config.enabled) {
        <p class="config-notice" role="status">
          <mat-icon aria-hidden="true">block</mat-icon>
          <span>
            {{ 'catalog.admin.mcp.off' | translate }}
            @if (config.reason) {
              <span class="config-reason">{{ config.reason }}</span>
            }
          </span>
        </p>
      }
    }

    @if (store.mcpError$ | async; as error) {
      <p class="config-notice" role="alert">
        <mat-icon aria-hidden="true">error_outline</mat-icon>
        <span>{{ 'catalog.admin.mcp.loadFailed' | translate: { error: error } }}</span>
      </p>
    }

    @if (store.mcpServers$ | async; as servers) {
      <div class="item-list">
        @for (server of sorted(servers); track server.id) {
          <div class="item-card" [class.is-disabled]="!server.enabled">
            <div class="item-main">
              <div class="item-title-row">
                <span class="item-title">{{ server.name }}</span>
                <span class="state-tag">{{ ('mcp.transport.' + server.transport) | translate }}</span>
                @if (server.auth !== 'none') {
                  <span class="state-tag">{{ ('mcp.auth.' + server.auth) | translate }}</span>
                }
                @if (server.auth === 'oauth' && server.connected) {
                  <span class="connect-state connect-state--on" [matTooltip]="'catalog.admin.mcp.signedInHint' | translate">
                    <mat-icon aria-hidden="true">check_circle</mat-icon>
                    {{ 'mcp.signedIn' | translate }}
                  </span>
                }
              </div>
              <div class="item-meta">
                <span class="mono" [matTooltip]="'mcp.toolPrefixHint' | translate: { slug: server.slug }">{{ server.slug }}__</span>
                @if (endpoint(server); as endpoint) {
                  <span class="mono">{{ endpoint }}</span>
                }
                <span>{{ toolSelectionKey(server) | translate: { count: server.tools?.length ?? 0 } }}</span>
                <span [matTooltip]="'catalog.admin.fields.sortOrder' | translate">#{{ server.sortOrder }}</span>
              </div>
              @if (headerNames(server); as names) {
                <div class="header-chips" [attr.aria-label]="'mcp.dialog.headers' | translate">
                  @for (name of names; track name) {
                    <span class="mono header-chip">{{ name }}</span>
                  }
                </div>
              }
              @if (server.description) {
                <p class="item-description">{{ server.description }}</p>
              }
              @if (server.unavailableReason) {
                <p class="item-warning">
                  <mat-icon aria-hidden="true">warning_amber</mat-icon>
                  <span>{{ 'mcp.unavailable' | translate: { reason: server.unavailableReason } }}</span>
                </p>
              }
              <p class="item-usage">
                <mat-icon aria-hidden="true">smart_toy</mat-icon>
                @if (usedBy(server); as names) {
                  {{ 'catalog.admin.mcp.usedBy' | translate: { names: names } }}
                } @else {
                  {{ 'catalog.admin.mcp.unused' | translate }}
                }
              </p>
            </div>

            <div class="item-controls">
              <div class="item-toggles">
                <mat-slide-toggle [checked]="server.enabled"
                                  [aria-label]="('catalog.admin.fields.enabled' | translate) + ': ' + server.name"
                                  (change)="setFlag(server, 'enabled', $event)">
                  {{ 'catalog.admin.fields.enabled' | translate }}
                </mat-slide-toggle>
                <mat-slide-toggle [checked]="server.availableToGuests"
                                  [aria-label]="('catalog.admin.fields.guests' | translate) + ': ' + server.name"
                                  (change)="setFlag(server, 'availableToGuests', $event)">
                  {{ 'catalog.admin.fields.guests' | translate }}
                </mat-slide-toggle>
              </div>
              <div class="item-actions">
                @if (server.auth === 'oauth' && server.connected) {
                  <button mat-icon-button type="button" (click)="signOut(server)"
                          [matTooltip]="'mcp.signOut' | translate"
                          [attr.aria-label]="('mcp.signOut' | translate) + ': ' + server.name">
                    <mat-icon>logout</mat-icon>
                  </button>
                }
                <button mat-icon-button type="button" (click)="test(server)"
                        [disabled]="tests[server.id]?.running"
                        [matTooltip]="'mcp.test.action' | translate"
                        [attr.aria-label]="('mcp.test.action' | translate) + ': ' + server.name">
                  @if (tests[server.id]?.running) {
                    <mat-spinner diameter="18"></mat-spinner>
                  } @else {
                    <mat-icon>play_circle</mat-icon>
                  }
                </button>
                <button mat-icon-button type="button" (click)="edit(server)"
                        [matTooltip]="'catalog.common.edit' | translate"
                        [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + server.name">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-icon-button type="button" class="danger-action" (click)="remove(server)"
                        [matTooltip]="'catalog.common.delete' | translate"
                        [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + server.name">
                  <mat-icon>delete_outline</mat-icon>
                </button>
              </div>
            </div>

            @if (tests[server.id]?.result; as result) {
              <app-mcp-test-result [result]="result" [server]="server" [editable]="true"
                                   [saving]="!!tests[server.id]?.savingTools"
                                   [signingIn]="!!tests[server.id]?.signingIn"
                                   [canSignIn]="store.mcpConfig?.encryption !== false"
                                   (signIn)="signIn(server)"
                                   (saveTools)="saveTools(server, $event)"
                                   (dismiss)="closeTest(server)"></app-mcp-test-result>
            }
          </div>
        } @empty {
          @if (!(store.mcpError$ | async)) {
            <div class="empty-state">
              <mat-icon aria-hidden="true">extension</mat-icon>
              <p>{{ 'catalog.admin.mcp.empty' | translate }}</p>
            </div>
          }
        }
      </div>
    }
  `,
  styleUrls: ['./catalog-admin-list.scss', '../mcp/mcp-list.scss']
})
export class McpServersTabComponent {
  readonly endpoint = serverEndpoint;
  readonly toolSelectionKey = toolSelectionKey;
  readonly sorted = sortServers;
  tests: Record<number, TestState | undefined> = {};

  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs,
    private translate: TranslateService
  ) {}

  /** The names of its headers (admin servers also return the values, which stay in the dialog). */
  headerNames(server: IMcpServerOut): string[] | null {
    const names = server.headerNames?.length ? server.headerNames : Object.keys(server.headers ?? {});
    return server.auth === 'headers' && names.length > 0 ? names : null;
  }

  /** The agents that use the server, or null when none does. */
  usedBy(server: IMcpServerOut): string | null {
    const names = this.store.personas.filter(p => p.mcpServers?.includes(server.slug)).map(p => p.name);
    return names.length > 0 ? names.join(', ') : null;
  }

  private dialogData(server: IMcpServerOut | null): McpServerDialogData {
    return {
      server,
      admin: true,
      config: this.store.mcpConfig,
      save: (id: number | null, body: IMcpServerCreate | IMcpServerUpdate) => this.store.saveMcpServer(id, body)
    };
  }

  async add(): Promise<void> {
    const saved = await this.dialogs.open<McpServerDialogComponent, McpServerDialogData, IMcpServerOut>(
      McpServerDialogComponent, this.dialogData(null)
    );
    if (saved) this.dialogs.notify('catalog.admin.mcp.saved', { name: saved.name });
  }

  async edit(server: IMcpServerOut): Promise<void> {
    const saved = await this.dialogs.open<McpServerDialogComponent, McpServerDialogData, IMcpServerOut>(
      McpServerDialogComponent, this.dialogData(server)
    );
    if (saved) {
      this.closeTest(server);  // The test was of the old settings
      this.dialogs.notify('catalog.admin.mcp.saved', { name: saved.name });
    }
  }

  async setFlag(server: IMcpServerOut, flag: 'enabled' | 'availableToGuests', change: MatSlideToggleChange): Promise<void> {
    try {
      await this.store.updateMcpServer(server, { [flag]: change.checked });
    } catch (error) {
      this.dialogs.notifyError(error);
      change.source.checked = !change.checked;  // Flip the switch back
    }
  }

  async test(server: IMcpServerOut): Promise<void> {
    this.tests[server.id] = { running: true };
    try {
      const result = await this.store.testMcpServer(server.id);
      this.tests[server.id] = { running: false, result };
    } catch (error) {
      this.tests[server.id] = {
        running: false,
        result: { ok: false, authRequired: false, error: describeHttpError(error, this.translate), tools: [] }
      };
    }
  }

  closeTest(server: IMcpServerOut): void {
    this.tests[server.id] = undefined;
  }

  async saveTools(server: IMcpServerOut, tools: string[] | null): Promise<void> {
    const test = this.tests[server.id];
    if (test) test.savingTools = true;
    try {
      await this.store.updateMcpServer(server, { tools });
      this.dialogs.notify('catalog.admin.mcp.selectionSaved', { name: server.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    } finally {
      if (test) test.savingTools = false;
    }
  }

  /** The admin's own sign-in; the provider sends the browser back to the MCP servers page. */
  async signIn(server: IMcpServerOut): Promise<void> {
    const test = this.tests[server.id];
    if (test) test.signingIn = true;
    try {
      const { authorizationUrl } = await this.store.connectMcpServer(server.id);
      window.location.href = authorizationUrl;
    } catch (error) {
      if (test) test.signingIn = false;
      this.dialogs.notifyError(error);
    }
  }

  async signOut(server: IMcpServerOut): Promise<void> {
    try {
      await this.store.disconnectMcpServer(server);
      this.closeTest(server);
      this.dialogs.notify('mcp.signedOutOf', { name: server.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }

  async remove(server: IMcpServerOut): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: this.dialogs.t('catalog.admin.mcp.deleteTitle', { name: server.name }),
      message: this.dialogs.t('catalog.admin.mcp.deleteMessage'),
      confirmLabel: this.dialogs.t('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.store.deleteMcpServer(server.id);
      this.closeTest(server);
      this.dialogs.notify('catalog.admin.deleted', { name: server.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }
}

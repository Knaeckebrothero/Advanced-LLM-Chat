import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { IMcpServerOut, IMcpTestResult, IMcpToolInfo } from '../data/models/mcp.model';

/**
 * The result of testing an MCP server (POST /api/mcp/servers/{id}/test): whether it answered,
 * its name and version, a sign-in when it needs one, and its tools with the server's annotations.
 * Where the server may be edited, the checkboxes pick the tools offered to agents: "all tools"
 * (null, also ones the server adds later) or exactly the checked ones; saving is up to the parent.
 */
@Component({
  selector: 'app-mcp-test-result',
  standalone: true,
  imports: [MatButtonModule, MatCheckboxModule, MatIconModule, MatProgressSpinnerModule, MatTooltipModule, TranslateModule],
  template: `
    <div class="test-result" role="status"
         [class.test-result--ok]="result.ok"
         [class.test-result--failed]="!result.ok && !result.authRequired"
         [class.test-result--auth]="!result.ok && result.authRequired">
      <mat-icon aria-hidden="true">{{ result.ok ? 'check_circle' : result.authRequired ? 'lock' : 'error_outline' }}</mat-icon>
      <span class="test-text">
        <span class="test-status">
          @if (result.ok) {
            {{ 'mcp.test.ok' | translate: { name: result.serverName || server.name } }}
          } @else if (result.authRequired) {
            {{ 'mcp.test.authRequired' | translate }}
          } @else {
            {{ 'mcp.test.failed' | translate }}
          }
        </span>
        @if (result.serverVersion) {
          <span class="test-detail">{{ 'mcp.test.version' | translate: { version: result.serverVersion } }}</span>
        }
        @if (result.protocolVersion) {
          <span class="test-detail">{{ 'mcp.test.protocol' | translate: { version: result.protocolVersion } }}</span>
        }
        @if (result.authRequired) {
          <span class="test-error">{{ (canSignIn ? 'mcp.test.authRequiredHint' : 'mcp.test.authRequiredNoSignIn') | translate }}</span>
        }
        @if (result.error) {
          <span class="test-error">{{ result.error }}</span>
        }
      </span>
      <button mat-icon-button type="button" class="test-close" (click)="dismiss.emit()"
              [matTooltip]="'catalog.common.close' | translate"
              [attr.aria-label]="'catalog.common.close' | translate">
        <mat-icon>close</mat-icon>
      </button>
    </div>

    @if (result.authRequired && canSignIn) {
      <div class="test-sign-in">
        <button mat-flat-button color="primary" type="button" (click)="signIn.emit()" [disabled]="signingIn">
          @if (signingIn) {
            <mat-spinner diameter="18"></mat-spinner>
          } @else {
            <mat-icon>login</mat-icon>
          }
          {{ 'mcp.signIn' | translate }}
        </button>
      </div>
    }

    @if (result.instructions) {
      <details class="test-instructions">
        <summary>{{ 'mcp.test.instructions' | translate }}</summary>
        <p>{{ result.instructions }}</p>
      </details>
    }

    @if (result.tools.length > 0) {
      <div class="mcp-tools">
        <div class="mcp-tools-head">
          <span class="mcp-tools-title">{{ 'mcp.test.tools' | translate: { count: result.tools.length } }}</span>
          @if (editable) {
            <mat-checkbox color="primary" [checked]="allTools" (change)="setAll($event.checked)">
              {{ 'mcp.test.allTools' | translate }}
            </mat-checkbox>
          }
        </div>
        @if (editable) {
          <p class="mcp-tools-hint">{{ 'mcp.test.selectionHint' | translate }}</p>
        }
        <ul class="mcp-tool-list">
          @for (tool of result.tools; track tool.name) {
            <li class="mcp-tool" [class.is-off]="!isChecked(tool)">
              @if (editable) {
                <mat-checkbox color="primary" class="mcp-tool-check"
                              [checked]="isChecked(tool)" [disabled]="allTools"
                              [aria-label]="tool.title || tool.name"
                              (change)="toggle(tool, $event.checked)"></mat-checkbox>
              } @else {
                <mat-icon class="mcp-tool-state" aria-hidden="true">{{ isChecked(tool) ? 'check' : 'remove' }}</mat-icon>
              }
              <div class="mcp-tool-main">
                <div class="mcp-tool-title-row">
                  <span class="mcp-tool-title">{{ tool.title || tool.name }}</span>
                  @if (tool.title && tool.title !== tool.name) {
                    <span class="mono mcp-tool-name">{{ tool.name }}</span>
                  }
                  @if (tool.readOnly) {
                    <span class="tool-hint tool-hint--safe" [matTooltip]="'mcp.test.readOnlyHint' | translate">
                      <mat-icon aria-hidden="true">visibility</mat-icon>
                      {{ 'mcp.test.readOnly' | translate }}
                    </span>
                  }
                  @if (tool.destructive) {
                    <span class="tool-hint tool-hint--danger" [matTooltip]="'mcp.test.destructiveHint' | translate">
                      <mat-icon aria-hidden="true">warning_amber</mat-icon>
                      {{ 'mcp.test.destructive' | translate }}
                    </span>
                  }
                  @if (!editable && !isChecked(tool)) {
                    <span class="state-tag">{{ 'mcp.test.notOffered' | translate }}</span>
                  }
                </div>
                @if (tool.description) {
                  <p class="mcp-tool-description" [title]="tool.description">{{ tool.description }}</p>
                }
              </div>
            </li>
          }
        </ul>
        @if (editable && !allTools && picked.size === 0) {
          <p class="mcp-tools-hint mcp-tools-hint--warning">{{ 'mcp.test.noneChecked' | translate }}</p>
        }
        @if (editable && isDirty) {
          <div class="mcp-tools-actions">
            <button mat-button type="button" (click)="reset()">{{ 'mcp.test.resetSelection' | translate }}</button>
            <button mat-flat-button color="primary" type="button" (click)="save()" [disabled]="saving">
              @if (saving) {
                <mat-spinner diameter="18"></mat-spinner>
              }
              {{ 'mcp.test.saveSelection' | translate }}
            </button>
          </div>
        }
      </div>
    } @else if (result.ok) {
      <p class="mcp-tools-hint">{{ 'mcp.test.noTools' | translate }}</p>
    }
  `,
  styleUrls: ['../catalog-admin/catalog-admin-list.scss', './mcp-test-result.component.scss']
})
export class McpTestResultComponent implements OnChanges {
  @Input({ required: true }) result!: IMcpTestResult;
  @Input({ required: true }) server!: IMcpServerOut;
  /** May change the server's tool selection (admins their servers, users their own). */
  @Input() editable = false;
  /** The selection is being saved. */
  @Input() saving = false;
  /** The user can sign in to this server here (OAuth with encryption on the server). */
  @Input() canSignIn = true;
  @Input() signingIn = false;
  @Output() signIn = new EventEmitter<void>();
  /** The new selection: null for all tools, else the names of the checked ones. */
  @Output() saveTools = new EventEmitter<string[] | null>();
  @Output() dismiss = new EventEmitter<void>();

  allTools = true;
  picked = new Set<string>();

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['result'] || changes['server']) this.reset();
  }

  /** Back to the server's selection. */
  reset(): void {
    const selection = this.server.tools;
    const names = this.result.tools.map(tool => tool.name);
    this.allTools = selection == null;
    this.picked = new Set(selection == null ? names : names.filter(name => selection.includes(name)));
  }

  isChecked(tool: IMcpToolInfo): boolean {
    return this.allTools || this.picked.has(tool.name);
  }

  /** Leaving "all tools" starts from every tool checked, so nothing changes until one is unchecked. */
  setAll(all: boolean): void {
    this.allTools = all;
    if (!all) this.picked = new Set(this.result.tools.map(tool => tool.name));
  }

  toggle(tool: IMcpToolInfo, checked: boolean): void {
    if (checked) this.picked.add(tool.name);
    else this.picked.delete(tool.name);
  }

  /** The selection differs from the server's. */
  get isDirty(): boolean {
    const selection = this.server.tools;
    if (this.allTools || selection == null) return this.allTools !== (selection == null);
    const listed = new Set(this.result.tools.map(tool => tool.name));
    // Names the server no longer lists don't count (they drop out when the selection is saved)
    const saved = new Set(selection.filter(name => listed.has(name)));
    return saved.size !== this.picked.size || [...this.picked].some(name => !saved.has(name));
  }

  save(): void {
    this.saveTools.emit(this.allTools ? null : this.result.tools.map(tool => tool.name).filter(name => this.picked.has(name)));
  }
}

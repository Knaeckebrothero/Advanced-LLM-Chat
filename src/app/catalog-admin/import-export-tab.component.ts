import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { ICatalogFile, IImportResult } from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError } from './catalog-admin.utils';

/** Download the catalog as JSON, and upload a catalog file (upsert by name, never deletes). */
@Component({
  selector: 'app-import-export-tab',
  standalone: true,
  imports: [MatButtonModule, MatCheckboxModule, MatIconModule, MatProgressSpinnerModule, TranslateModule],
  template: `
    <div class="transfer-grid">
      <!-- Export -->
      <section class="item-card transfer-card">
        <div class="item-main">
          <div class="item-title-row">
            <mat-icon aria-hidden="true">download</mat-icon>
            <h3 class="item-title">{{ 'catalog.admin.transfer.exportTitle' | translate }}</h3>
          </div>
          <p class="item-description">{{ 'catalog.admin.transfer.exportIntro' | translate }}</p>
          <mat-checkbox [checked]="includeKeys" (change)="includeKeys = $event.checked">
            {{ 'catalog.admin.transfer.includeKeys' | translate }}
          </mat-checkbox>
          @if (includeKeys) {
            <p class="transfer-warning" role="alert">
              <mat-icon aria-hidden="true">warning</mat-icon>
              <span>{{ 'catalog.admin.transfer.includeKeysWarning' | translate }}</span>
            </p>
          }
          @if (exportError) {
            <p class="transfer-warning" role="alert">
              <mat-icon aria-hidden="true">error_outline</mat-icon>
              <span>{{ exportError }}</span>
            </p>
          }
          <div class="transfer-actions">
            <button mat-flat-button color="primary" type="button" (click)="export()" [disabled]="exporting">
              @if (exporting) {
                <mat-spinner diameter="18"></mat-spinner>
              } @else {
                <mat-icon>download</mat-icon>
              }
              {{ 'catalog.admin.transfer.download' | translate }}
            </button>
          </div>
        </div>
      </section>

      <!-- Import -->
      <section class="item-card transfer-card">
        <div class="item-main">
          <div class="item-title-row">
            <mat-icon aria-hidden="true">upload</mat-icon>
            <h3 class="item-title">{{ 'catalog.admin.transfer.importTitle' | translate }}</h3>
          </div>
          <p class="item-description">{{ 'catalog.admin.transfer.importIntro' | translate }}</p>
          <input #fileInput type="file" accept="application/json,.json" class="hidden-input"
                 (change)="onFileSelected($event)">
          <div class="transfer-actions">
            <button mat-stroked-button type="button" (click)="fileInput.click()" [disabled]="importing">
              @if (importing) {
                <mat-spinner diameter="18"></mat-spinner>
              } @else {
                <mat-icon>upload_file</mat-icon>
              }
              {{ 'catalog.admin.transfer.chooseFile' | translate }}
            </button>
            @if (fileName) {
              <span class="mono file-name">{{ fileName }}</span>
            }
          </div>

          @if (importError) {
            <p class="transfer-warning" role="alert">
              <mat-icon aria-hidden="true">error_outline</mat-icon>
              <span>{{ importError }}</span>
            </p>
          }

          @if (result) {
            <div class="import-result" role="status">
              <table>
                <thead>
                  <tr>
                    <th scope="col"></th>
                    <th scope="col">{{ 'catalog.admin.transfer.created' | translate }}</th>
                    <th scope="col">{{ 'catalog.admin.transfer.updated' | translate }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">{{ 'catalog.admin.tabs.providers' | translate }}</th>
                    <td>{{ result.providers.created }}</td>
                    <td>{{ result.providers.updated }}</td>
                  </tr>
                  <tr>
                    <th scope="row">{{ 'catalog.admin.tabs.models' | translate }}</th>
                    <td>{{ result.models.created }}</td>
                    <td>{{ result.models.updated }}</td>
                  </tr>
                  <tr>
                    <th scope="row">{{ 'catalog.admin.tabs.personas' | translate }}</th>
                    <td>{{ result.personas.created }}</td>
                    <td>{{ result.personas.updated }}</td>
                  </tr>
                </tbody>
              </table>
              @if (result.errors.length > 0) {
                <p class="result-errors-title">{{ 'catalog.admin.transfer.errors' | translate: { count: result.errors.length } }}</p>
                <ul class="result-errors">
                  @for (error of result.errors; track $index) {
                    <li>{{ error }}</li>
                  }
                </ul>
              }
            </div>
          }
        </div>
      </section>
    </div>
  `,
  styleUrls: ['./catalog-admin-list.scss'],
  styles: [`
    .transfer-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
    }

    .transfer-card .item-main { gap: 12px; }

    .transfer-card .item-title { margin: 0; }

    .transfer-card .item-title-row mat-icon { color: var(--theme-text-accent); }

    .transfer-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;

      mat-spinner { display: inline-block; margin-right: 8px; }
    }

    .hidden-input { display: none; }

    .file-name { color: var(--theme-text-secondary); }

    .transfer-warning {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin: 0;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--theme-tier-untrusted-bg);
      color: var(--theme-tier-untrusted);
      font-size: 0.8rem;
      line-height: 1.45;
      overflow-wrap: anywhere;

      mat-icon { flex-shrink: 0; font-size: 18px; width: 18px; height: 18px; }
    }

    .import-result {
      font-size: 0.85rem;

      table { border-collapse: collapse; width: 100%; max-width: 360px; }

      th, td {
        padding: 6px 10px;
        border-bottom: 1px solid var(--theme-border);
        text-align: right;
        font-variant-numeric: tabular-nums;
      }

      th[scope='row'], thead th:first-child { text-align: left; font-weight: 500; }

      thead th { color: var(--theme-text-secondary); font-weight: 600; font-size: 0.75rem; }
    }

    .result-errors-title {
      margin: 12px 0 4px;
      font-weight: 600;
      color: var(--theme-tier-untrusted);
    }

    .result-errors {
      margin: 0;
      padding-left: 20px;
      color: var(--theme-text-secondary);
      overflow-wrap: anywhere;
    }
  `]
})
export class ImportExportTabComponent {
  includeKeys = false;
  exporting = false;
  importing = false;
  exportError: string | null = null;
  importError: string | null = null;
  fileName: string | null = null;
  result: IImportResult | null = null;

  constructor(
    private store: CatalogAdminStore,
    private translate: TranslateService
  ) {}

  async export(): Promise<void> {
    this.exporting = true;
    this.exportError = null;
    try {
      const file = await this.store.exportCatalog(this.includeKeys);
      const blob = new Blob([JSON.stringify(file, null, 2) + '\n'], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `model-catalog-${new Date().toISOString().slice(0, 10)}${this.includeKeys ? '-with-keys' : ''}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      this.exportError = describeHttpError(error, this.translate);
    } finally {
      this.exporting = false;
    }
  }

  async onFileSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';  // Picking the same file again still triggers a change
    if (!file) return;

    this.fileName = file.name;
    this.importError = null;
    this.result = null;

    let parsed: ICatalogFile;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      this.importError = this.translate.instant('catalog.admin.transfer.invalidJson');
      return;
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      this.importError = this.translate.instant('catalog.admin.transfer.invalidFile');
      return;
    }

    this.importing = true;
    try {
      this.result = await this.store.importCatalog(parsed);
    } catch (error) {
      this.importError = describeHttpError(error, this.translate);
    } finally {
      this.importing = false;
    }
  }
}

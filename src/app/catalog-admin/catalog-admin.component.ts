import { Component, OnInit } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS, MatFormFieldDefaultOptions } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { TranslateModule } from '@ngx-translate/core';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { ModelsTabComponent } from './models-tab.component';
import { PersonasTabComponent } from './personas-tab.component';
import { ImportExportTabComponent } from './import-export-tab.component';

/**
 * The Agents page for admins (route /agents, loaded on demand): agents (personas in the API),
 * the models with a read-only view of their providers, and the JSON import and export.
 */
@Component({
  selector: 'app-catalog-admin',
  standalone: true,
  imports: [
    AsyncPipe,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslateModule,
    ModelsTabComponent,
    PersonasTabComponent,
    ImportExportTabComponent
  ],
  providers: [
    CatalogAdminStore,
    CatalogAdminDialogs,
    // Hints may wrap in narrow fields; let them take the room they need
    {
      provide: MAT_FORM_FIELD_DEFAULT_OPTIONS,
      useValue: { appearance: 'outline', subscriptSizing: 'dynamic' } as MatFormFieldDefaultOptions
    }
  ],
  templateUrl: './catalog-admin.component.html',
  styleUrls: ['./catalog-admin.component.scss']
})
export class CatalogAdminComponent implements OnInit {
  constructor(public store: CatalogAdminStore) {}

  ngOnInit(): void {
    this.store.loadAll();
  }
}

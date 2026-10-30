import { Component, OnInit } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS, MatFormFieldDefaultOptions } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { TranslateModule } from '@ngx-translate/core';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { ProvidersTabComponent } from './providers-tab.component';
import { ModelsTabComponent } from './models-tab.component';
import { PersonasTabComponent } from './personas-tab.component';
import { ImportExportTabComponent } from './import-export-tab.component';

const TAB_KEY = 'catalogAdminTab';

/**
 * Model catalog management for admins (route /admin/catalog, loaded on demand):
 * providers, models, personas, and the JSON import and export.
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
    MatTabsModule,
    TranslateModule,
    ProvidersTabComponent,
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
  selectedTab = 0;

  constructor(
    public store: CatalogAdminStore,
    private router: Router
  ) {
    try {
      this.selectedTab = Number(sessionStorage.getItem(TAB_KEY)) || 0;
    } catch {
      this.selectedTab = 0;
    }
  }

  ngOnInit(): void {
    this.store.loadAll();
  }

  onTabChange(index: number): void {
    this.selectedTab = index;
    try {
      sessionStorage.setItem(TAB_KEY, String(index));
    } catch {
      // Storage may be unavailable (private mode); the tab is just not remembered
    }
  }

  back(): void {
    this.router.navigate(['/']);
  }
}

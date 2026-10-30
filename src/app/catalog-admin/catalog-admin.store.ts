import { Injectable } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject } from 'rxjs';
import { TranslateService } from '@ngx-translate/core';
import { ApiService } from '../services/api.service';
import { CatalogService } from '../services/catalog.service';
import {
  ICatalogFile,
  IFetchedModel,
  IFetchModelsResponse,
  IImportResult,
  IModelCreate,
  IModelOut,
  IModelTestResult,
  IModelUpdate,
  IPersonaCreate,
  IPersonaOut,
  IPersonaUpdate,
  IProviderOut,
  IToolStatus,
  TOOL_GROUPS
} from '../data/models/catalog.model';
import { describeHttpError } from './catalog-admin.utils';

export type AdminLoadState = 'loading' | 'ready' | 'forbidden' | 'error';

/**
 * State of the Agents page: providers (read-only, configured on the server), models and
 * personas as the admin API returns them, the tool groups, plus the write operations.
 * After every change the lists are reloaded, and so is the public catalog the pickers use.
 */
@Injectable()
export class CatalogAdminStore {
  readonly providers$ = new BehaviorSubject<IProviderOut[]>([]);
  readonly models$ = new BehaviorSubject<IModelOut[]>([]);
  readonly personas$ = new BehaviorSubject<IPersonaOut[]>([]);
  readonly tools$ = new BehaviorSubject<IToolStatus[]>([]);
  readonly state$ = new BehaviorSubject<AdminLoadState>('loading');
  readonly loadError$ = new BehaviorSubject<string | null>(null);

  constructor(
    private api: ApiService,
    private catalog: CatalogService,
    private translate: TranslateService
  ) {}

  get providers(): IProviderOut[] {
    return this.providers$.value;
  }

  get models(): IModelOut[] {
    return this.models$.value;
  }

  get personas(): IPersonaOut[] {
    return this.personas$.value;
  }

  get tools(): IToolStatus[] {
    return this.tools$.value;
  }

  async loadAll(): Promise<void> {
    this.state$.next('loading');
    this.loadError$.next(null);
    try {
      const [providers, models, personas, tools] = await Promise.all([
        this.api.getAdminProviders(),
        this.api.getAdminModels(),
        this.api.getAdminPersonas(),
        this.loadTools()
      ]);
      this.providers$.next(providers ?? []);
      this.models$.next(models ?? []);
      this.personas$.next(personas ?? []);
      this.tools$.next(tools);
      this.state$.next('ready');
    } catch (error) {
      if (error instanceof HttpErrorResponse && (error.status === 401 || error.status === 403)) {
        this.state$.next('forbidden');
      } else {
        this.loadError$.next(describeHttpError(error, this.translate));
        this.state$.next('error');
      }
    }
  }

  /**
   * The tool groups the server offers. A failed request doesn't block the page: all groups are
   * then listed as available (the server only gives an agent the tools it has).
   */
  private async loadTools(): Promise<IToolStatus[]> {
    try {
      const tools = await this.api.getAdminTools();
      if (Array.isArray(tools) && tools.length > 0) return tools;
    } catch (error) {
      console.warn('Tool groups could not be loaded:', error);
    }
    return TOOL_GROUPS.map(id => ({ id, available: true, reason: null }));
  }

  private async reload(lists: Array<'providers' | 'models' | 'personas'>): Promise<void> {
    const tasks: Promise<void>[] = [];
    if (lists.includes('providers')) {
      tasks.push(this.api.getAdminProviders().then(p => this.providers$.next(p ?? [])));
    }
    if (lists.includes('models')) {
      tasks.push(this.api.getAdminModels().then(m => this.models$.next(m ?? [])));
    }
    if (lists.includes('personas')) {
      tasks.push(this.api.getAdminPersonas().then(p => this.personas$.next(p ?? [])));
    }
    await Promise.all(tasks);
    // The pickers show the public view of the catalog
    this.catalog.refresh();
  }

  // Providers (read-only)

  fetchProviderModels(id: number): Promise<IFetchModelsResponse> {
    return this.api.fetchProviderModels(id);
  }

  /** Add models picked from a provider's model list, with default settings. */
  async addFetchedModels(provider: IProviderOut, fetched: IFetchedModel[]): Promise<{ added: number; errors: string[] }> {
    const errors: string[] = [];
    let added = 0;
    const nextSortOrder = Math.max(0, ...this.models.map(m => m.sortOrder)) + 10;
    for (const [index, model] of fetched.entries()) {
      const create: IModelCreate = {
        providerId: provider.id,
        displayName: model.id,
        modelId: model.id,
        supportsTools: true,
        supportsVision: false,
        reasoning: 'none',
        reasoningPassback: false,
        contextWindow: model.contextWindow ?? null,
        isAuxiliary: false,
        availableToGuests: false,
        enabled: true,
        sortOrder: nextSortOrder + index * 10
      };
      try {
        await this.api.createModel(create);
        added++;
      } catch (error) {
        errors.push(`${model.id}: ${describeHttpError(error, this.translate)}`);
      }
    }
    await this.reload(['providers', 'models']);
    return { added, errors };
  }

  // Models

  async saveModel(id: number | null, data: IModelCreate | IModelUpdate): Promise<IModelOut> {
    const saved = id === null
      ? await this.api.createModel(data as IModelCreate)
      : await this.api.updateModel(id, data as IModelUpdate);
    await this.reload(['providers', 'models']);
    return saved;
  }

  /** Flip a switch in the list (enabled, guests) without opening the dialog. */
  async updateModelFlags(model: IModelOut, changes: Pick<IModelUpdate, 'enabled' | 'availableToGuests'>): Promise<void> {
    const updated = await this.api.updateModel(model.id, changes);
    this.models$.next(this.models.map(m => (m.id === model.id ? { ...m, ...updated } : m)));
    this.catalog.refresh();
  }

  async deleteModel(id: number): Promise<void> {
    await this.api.deleteModel(id);
    await this.reload(['providers', 'models', 'personas']);
  }

  testModel(id: number): Promise<IModelTestResult> {
    return this.api.testModel(id);
  }

  // Personas

  async savePersona(id: number | null, data: IPersonaCreate | IPersonaUpdate): Promise<IPersonaOut> {
    const saved = id === null
      ? await this.api.createPersona(data as IPersonaCreate)
      : await this.api.updatePersona(id, data as IPersonaUpdate);
    await this.reload(['personas']);
    return saved;
  }

  async deletePersona(id: number): Promise<void> {
    await this.api.deletePersona(id);
    await this.reload(['personas']);
  }

  /** A name for a copy that no other persona has yet ("Name (copy)", "Name (copy 2)", ...). */
  copyName(name: string): string {
    const taken = new Set(this.personas.map(p => p.name.trim().toLowerCase()));
    for (let n = 1; ; n++) {
      const candidate = n === 1
        ? this.translate.instant('catalog.admin.personas.copyName', { name })
        : this.translate.instant('catalog.admin.personas.copyNameN', { name, n });
      if (!taken.has(candidate.trim().toLowerCase())) return candidate;
    }
  }

  // Import and export

  exportCatalog(): Promise<ICatalogFile> {
    return this.api.exportCatalog();
  }

  async importCatalog(file: ICatalogFile): Promise<IImportResult> {
    const result = await this.api.importCatalog(file);
    // Providers aren't imported, but their model counts change
    await this.reload(['providers', 'models', 'personas']);
    return result;
  }
}

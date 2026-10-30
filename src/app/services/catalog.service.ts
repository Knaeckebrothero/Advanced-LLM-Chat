// src/app/services/catalog.service.ts
import { Injectable } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { distinctUntilChanged, map } from 'rxjs/operators';
import { ApiService } from './api.service';
import { AuthService } from '../auth/auth.service';
import { DBService } from '../data/db.service';
import { IPublicModel, IPublicPersona } from '../data/models/catalog.model';

/** Models of one provider, in catalog order. */
export interface ModelGroup {
  providerName: string;
  models: IPublicModel[];
}

/**
 * The model catalog as the pickers see it (GET /api/models and /api/personas).
 *
 * The lists depend on the user (guests only see guest models), so they are reloaded
 * whenever the user changes. A failed request counts as an empty catalog: the backend
 * then answers with its environment model and the chat works as without a catalog.
 * Only when the backend can't be reached at all is the last list from IndexedDB used.
 */
@Injectable({ providedIn: 'root' })
export class CatalogService {
  private modelsSubject = new BehaviorSubject<IPublicModel[]>([]);
  private personasSubject = new BehaviorSubject<IPublicPersona[]>([]);
  private loadingPromise: Promise<void> | null = null;

  public readonly models$: Observable<IPublicModel[]> = this.modelsSubject.asObservable();
  public readonly personas$: Observable<IPublicPersona[]> = this.personasSubject.asObservable();

  /** Models grouped by provider, groups in the order of their first model. */
  public readonly modelGroups$: Observable<ModelGroup[]> = this.models$.pipe(
    map(models => CatalogService.groupByProvider(models))
  );

  /** Whether there is anything to pick; the pickers are hidden otherwise. */
  public readonly hasModels$: Observable<boolean> = this.models$.pipe(
    map(models => models.length > 0),
    distinctUntilChanged()
  );

  constructor(
    private apiService: ApiService,
    private authService: AuthService,
    private dbService: DBService
  ) {
    // Load once auth is ready, and again for every new user (login, logout, guest session)
    this.authService.currentUser$.pipe(
      map(user => (user ? `${user.id}:${user.email}` : null)),
      distinctUntilChanged()
    ).subscribe(userKey => {
      if (userKey) {
        this.refresh();
      } else {
        this.modelsSubject.next([]);
        this.personasSubject.next([]);
      }
    });
  }

  get models(): IPublicModel[] {
    return this.modelsSubject.value;
  }

  get personas(): IPublicPersona[] {
    return this.personasSubject.value;
  }

  get hasModels(): boolean {
    return this.modelsSubject.value.length > 0;
  }

  getModel(id: number | null | undefined): IPublicModel | undefined {
    if (id === null || id === undefined) return undefined;
    return this.modelsSubject.value.find(m => m.id === id);
  }

  getPersona(id: number | null | undefined): IPublicPersona | undefined {
    if (id === null || id === undefined) return undefined;
    return this.personasSubject.value.find(p => p.id === id);
  }

  /**
   * The model the backend will answer with, following its resolver order:
   * the conversation's model, then the user's default, then the first model of the catalog.
   * Null when the catalog is empty (the environment model answers).
   */
  resolveModel(
    modelId: number | null | undefined,
    defaultModelId: number | null | undefined,
    models: IPublicModel[] = this.modelsSubject.value
  ): IPublicModel | null {
    if (models.length === 0) return null;
    return models.find(m => m.id === modelId)
      ?? models.find(m => m.id === defaultModelId)
      ?? models[0];
  }

  /** Reload both lists. Concurrent calls share one request. */
  refresh(): Promise<void> {
    if (!this.loadingPromise) {
      this.loadingPromise = Promise.all([this.loadModels(), this.loadPersonas()])
        .then(() => undefined)
        .finally(() => { this.loadingPromise = null; });
    }
    return this.loadingPromise;
  }

  private async loadModels(): Promise<void> {
    try {
      const models = await this.apiService.getModels();
      this.modelsSubject.next(Array.isArray(models) ? models : []);
      await this.dbService.saveCatalogCache({ id: 'models', items: this.modelsSubject.value, fetchedAt: Date.now() });
    } catch (error) {
      if (CatalogService.isOffline(error)) {
        const cached = await this.dbService.getCatalogCache('models').catch(() => undefined);
        this.modelsSubject.next(cached?.items ?? []);
      } else {
        // No catalog on this backend (or no access): behave as without a catalog
        console.info('Model catalog not available, using the backend default model');
        this.modelsSubject.next([]);
      }
    }
  }

  private async loadPersonas(): Promise<void> {
    try {
      const personas = await this.apiService.getPersonas();
      this.personasSubject.next(Array.isArray(personas) ? personas : []);
      await this.dbService.saveCatalogCache({ id: 'personas', items: this.personasSubject.value, fetchedAt: Date.now() });
    } catch (error) {
      if (CatalogService.isOffline(error)) {
        const cached = await this.dbService.getCatalogCache('personas').catch(() => undefined);
        this.personasSubject.next(cached?.items ?? []);
      } else {
        this.personasSubject.next([]);
      }
    }
  }

  /** Status 0: the request never reached the backend (offline, or the server is down). */
  private static isOffline(error: unknown): boolean {
    return error instanceof HttpErrorResponse && error.status === 0;
  }

  static groupByProvider(models: IPublicModel[]): ModelGroup[] {
    const groups: ModelGroup[] = [];
    const byName = new Map<string, ModelGroup>();
    for (const model of models) {
      let group = byName.get(model.providerName);
      if (!group) {
        group = { providerName: model.providerName, models: [] };
        byName.set(model.providerName, group);
        groups.push(group);
      }
      group.models.push(model);
    }
    return groups;
  }
}

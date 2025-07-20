import { BehaviorSubject, Observable } from 'rxjs';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';

export interface SyncResult {
  success: boolean;
  itemsUpdated: number;
  errors?: string[];
}

export interface SyncMetadata {
  hash: string;
  lastSynced: Date;
  version?: number;
}

export abstract class BaseRepository<T> {
  protected cache$ = new BehaviorSubject<T[]>([]);
  protected isSyncing$ = new BehaviorSubject<boolean>(false);
  protected lastSyncTime: Date | null = null;

  constructor(
    protected dbService: DBService,
    protected apiService: ApiService
  ) {}

  abstract getAll(): Observable<T[]>;
  abstract getById(id: string | number): Observable<T | null>;
  abstract save(item: T): Promise<T>;
  abstract delete(id: string | number): Promise<void>;
  abstract computeHash(items: T[]): Promise<string>;
  abstract sync(): Promise<SyncResult>;

  get data$(): Observable<T[]> {
    return this.cache$.asObservable();
  }

  get syncing$(): Observable<boolean> {
    return this.isSyncing$.asObservable();
  }

  protected async updateCache(items: T[]): Promise<void> {
    this.cache$.next(items);
  }

  protected async isStale(maxAgeHours: number = 24): Promise<boolean> {
    if (!this.lastSyncTime) return true;
    
    const now = new Date();
    const diffHours = (now.getTime() - this.lastSyncTime.getTime()) / (1000 * 60 * 60);
    return diffHours > maxAgeHours;
  }

  protected async computeHashFromString(data: string): Promise<string> {
    const encoder = new TextEncoder();
    const dataBuffer = encoder.encode(data);
    const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }
}
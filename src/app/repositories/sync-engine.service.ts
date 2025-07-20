import { Injectable } from '@angular/core';
import { BehaviorSubject, interval, merge, Observable } from 'rxjs';
import { filter, switchMap } from 'rxjs/operators';
import { SettingsRepository } from './settings.repository';
import { ConversationRepository } from './conversation.repository';
import { ApiService } from '../services/api.service';
import { environment } from '../environments/environment';

export interface SyncManifest {
  settings: {
    hash: string;
    timestamp: Date;
  };
  conversations: Array<{
    id: number;
    hash: string;
    lastSynced: Date;
  }>;
}

export interface SyncStatus {
  isOnline: boolean;
  isSyncing: boolean;
  lastSync: Date | null;
  pendingOperations: number;
}

@Injectable({
  providedIn: 'root'
})
export class SyncEngineService {
  private syncStatus$ = new BehaviorSubject<SyncStatus>({
    isOnline: true,
    isSyncing: false,
    lastSync: null,
    pendingOperations: 0
  });

  private connectionCheckInterval: any;
  private periodicSyncInterval: any;
  private readonly SYNC_INTERVAL = 5 * 60 * 1000; // 5 minutes
  private readonly CONNECTION_CHECK_INTERVAL = 30 * 1000; // 30 seconds

  constructor(
    private settingsRepository: SettingsRepository,
    private conversationRepository: ConversationRepository,
    private apiService: ApiService
  ) {
    this.initialize();
  }

  private initialize() {
    // Set up connection monitoring
    this.setupConnectionMonitoring();
    
    // Set up periodic sync
    this.setupPeriodicSync();
    
    // Perform initial sync
    this.performInitialSync();
  }

  /**
   * Get current sync status
   */
  get status$(): Observable<SyncStatus> {
    return this.syncStatus$.asObservable();
  }

  /**
   * Manually trigger sync
   */
  async syncNow(): Promise<void> {
    await this.performSync();
  }

  /**
   * Sync specific conversation
   */
  async syncConversation(conversationId: number): Promise<void> {
    const status = this.syncStatus$.getValue();
    if (!status.isOnline || status.isSyncing) {
      console.log('Skip conversation sync - offline or already syncing');
      return;
    }

    // Sync specific conversation
    await this.conversationRepository.syncConversation(conversationId);
  }

  /**
   * Main sync logic following the simplified strategy
   */
  private async performSync(): Promise<void> {
    const status = this.syncStatus$.getValue();
    if (!status.isOnline || status.isSyncing) {
      console.log('Skip sync - offline or already syncing');
      return;
    }

    this.updateStatus({ isSyncing: true });

    try {
      // Step 1: Sync settings
      console.log('Syncing settings...');
      const settingsResult = await this.settingsRepository.sync();
      console.log(`Settings sync result:`, settingsResult);

      // Step 2: Sync last 5 conversations
      console.log('Syncing recent conversations...');
      const conversationResult = await this.conversationRepository.syncRecent(5);
      console.log(`Conversation sync result:`, conversationResult);

      this.updateStatus({
        lastSync: new Date(),
        isSyncing: false
      });
    } catch (error) {
      console.error('Sync failed:', error);
      this.updateStatus({ isSyncing: false });
    }
  }

  /**
   * Initial sync on startup
   */
  private async performInitialSync(): Promise<void> {
    console.log('Performing initial sync...');
    await this.performSync();
  }

  /**
   * Set up connection monitoring
   */
  private setupConnectionMonitoring() {
    this.connectionCheckInterval = setInterval(async () => {
      const isOnline = await this.checkConnection();
      const status = this.syncStatus$.getValue();
      
      if (isOnline !== status.isOnline) {
        this.updateStatus({ isOnline });
        
        if (isOnline && !status.isOnline) {
          console.log('Connection restored, triggering sync...');
          await this.performSync();
        }
      }
    }, this.CONNECTION_CHECK_INTERVAL);
  }

  /**
   * Set up periodic sync
   */
  private setupPeriodicSync() {
    this.periodicSyncInterval = setInterval(async () => {
      const status = this.syncStatus$.getValue();
      if (status.isOnline) {
        console.log('Performing periodic sync...');
        await this.performSync();
      }
    }, this.SYNC_INTERVAL);
  }

  /**
   * Check if backend is available
   */
  private async checkConnection(): Promise<boolean> {
    try {
      const response = await fetch(`${environment.apiUrl}/api/auth/me`, {
        method: 'GET',
        credentials: 'include'
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  /**
   * Update sync status
   */
  private updateStatus(update: Partial<SyncStatus>) {
    const current = this.syncStatus$.getValue();
    this.syncStatus$.next({ ...current, ...update });
  }

  /**
   * Clean up resources
   */
  destroy() {
    if (this.connectionCheckInterval) {
      clearInterval(this.connectionCheckInterval);
    }
    if (this.periodicSyncInterval) {
      clearInterval(this.periodicSyncInterval);
    }
  }
}
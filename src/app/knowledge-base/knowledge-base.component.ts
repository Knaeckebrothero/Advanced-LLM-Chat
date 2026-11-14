import { Component, DestroyRef, OnInit, computed, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { combineLatest } from 'rxjs';
import { skip } from 'rxjs/operators';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS, MatFormFieldDefaultOptions, MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IKBFile, IKBNote, IKBNoteSummary, IKBSearchHit, IKBVault, KB_MEMORY_SLUG, NoteStatus } from '../data/models/knowledge-base.model';
import { FileTileComponent } from '../components/file-tile/file-tile.component';
import { ChatStateService } from '../services/chat-state.service';
import { FamilyModeService } from '../services/family-mode.service';
import { ConfirmDialogData } from '../catalog-admin/confirm-dialog.component';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { KnowledgeBaseStore, kbErrorDetail } from './knowledge-base.store';
import { NoteViewComponent } from './note-view.component';
import { NoteEditorComponent } from './note-editor.component';
import { NoteHistoryComponent } from './note-history.component';
import { formatDate } from './kb-labels';
import { confirmDialog } from './kb-confirm';
import { NOTE_ROUTE, plainText, slugify } from './kb-markdown';

type PaneMode = 'view' | 'edit' | 'history';

/**
 * The Knowledge base page (route /knowledge-base, loaded on demand), for signed-in users: the
 * notes their agents keep, to read, search, correct, archive, delete and export for Obsidian.
 * On wide screens the list and the open note sit side by side; on phones they take turns.
 *
 * The query parameter vault picks the knowledge base: none for the shared one, an agent's id for
 * its own (the picker shows when there is more than one). Every navigation on the page keeps it.
 * The memory of the knowledge base is pinned above the list.
 */
@Component({
  selector: 'app-knowledge-base',
  standalone: true,
  imports: [
    FormsModule,
    FileTileComponent,
    MatButtonModule,
    MatButtonToggleModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslateModule,
    NoteViewComponent,
    NoteEditorComponent,
    NoteHistoryComponent
  ],
  providers: [
    KnowledgeBaseStore,
    {
      provide: MAT_FORM_FIELD_DEFAULT_OPTIONS,
      useValue: { appearance: 'outline', subscriptSizing: 'dynamic' } as MatFormFieldDefaultOptions
    }
  ],
  templateUrl: './knowledge-base.component.html',
  styleUrls: ['./kb-pane.scss', './knowledge-base.component.scss']
})
export class KnowledgeBaseComponent implements OnInit {
  readonly mode = signal<PaneMode>('view');
  /** A new note is being written (with this title to start from), or null. */
  readonly creating = signal<{ title: string } | null>(null);
  readonly exporting = signal(false);
  searchText = '';

  /** Something is open in the note pane (on phones the list hides then). */
  readonly hasSelection = computed(() => this.creating() !== null || this.store.slug() !== null);

  private editorDirty = false;
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    readonly store: KnowledgeBaseStore,
    private route: ActivatedRoute,
    private router: Router,
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private chatState: ChatStateService,
    private destroyRef: DestroyRef,
    private familyMode: FamilyModeService
  ) {}

  ngOnInit(): void {
    this.reloadWhenFamilyModeSwitches();
    this.store.loadVaults();
    let listLoaded = false;
    combineLatest([this.route.paramMap, this.route.queryParamMap]).pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(([params, query]) => {
        const vault = Number(query.get('vault')) || 0;
        if (vault !== this.store.vault()) {
          this.store.setVault(vault);
        } else if (!listLoaded) {
          this.store.loadList();
        }
        listLoaded = true;
        this.creating.set(null);
        this.mode.set('view');
        this.editorDirty = false;
        this.store.open(params.get('slug'));
      });
  }

  /**
   * The server leaves out what is hidden while this device is in family mode: when the switch
   * changes, everything shown is loaded again, and a knowledge base that is hidden now (a hidden
   * agent's own) gives way to the shared one.
   */
  private reloadWhenFamilyModeSwitches(): void {
    this.familyMode.active$.pipe(skip(1), takeUntilDestroyed(this.destroyRef)).subscribe(async () => {
      await this.store.loadVaults();
      if (!this.store.vaults().some(vault => vault.id === this.store.vault())) {
        this.router.navigate([NOTE_ROUTE]);
        return;
      }
      this.store.loadList();
      this.store.open(this.store.slug());
    });
  }

  /** Go to a note (or the list) of the knowledge base shown. */
  private go(slug?: string): void {
    this.router.navigate(slug ? [NOTE_ROUTE, slug] : [NOTE_ROUTE], { queryParamsHandling: 'preserve' });
  }

  // The knowledge bases and the memory

  vaultName(vault: IKBVault): string {
    if (vault.id === 0) return this.translate.instant('knowledgeBase.vault.shared');
    return vault.personaName ?? this.translate.instant('knowledgeBase.vault.deletedAgent', { id: vault.id });
  }

  async setVault(vault: number): Promise<void> {
    if (vault === this.store.vault() || !(await this.leaveEditor())) return;
    this.searchText = '';
    this.router.navigate([NOTE_ROUTE], { queryParams: { vault: vault || null } });
  }

  openMemory(): void {
    this.select(KB_MEMORY_SLUG);
  }

  // The list

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.store.setQuery(this.searchText), 250);
  }

  clearSearch(): void {
    this.searchText = '';
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.store.setQuery('');
  }

  setStatus(status: NoteStatus): void {
    this.store.setStatus(status);
  }

  pickTag(tag: string): void {
    this.searchText = '';
    this.store.setTag(tag);
  }

  /** A tag picked on a note: on phones the list with that tag shows. */
  showTag(tag: string): void {
    this.searchText = '';
    if (this.store.tag() !== tag) this.store.setTag(tag);
    if (window.matchMedia('(max-width: 768px)').matches) this.go();
  }

  snippet(item: IKBNoteSummary | IKBSearchHit): string | null {
    return 'snippet' in item ? plainText(item.snippet) : null;
  }

  /** The first image a note keeps, shown next to it in the list. */
  thumb(item: IKBNoteSummary): IKBFile | null {
    return item.files?.find(file => file.mimeType.startsWith('image/')) ?? null;
  }

  date(value: string | null): string {
    return formatDate(value, this.translate);
  }

  async select(slug: string): Promise<void> {
    if (!(await this.leaveEditor())) return;
    this.creating.set(null);
    this.mode.set('view');
    this.go(slug);
  }

  async newNote(title = ''): Promise<void> {
    if (!(await this.leaveEditor())) return;
    this.creating.set({ title });
  }

  backToList(): void {
    this.go();
  }

  // The note pane

  onDirtyChange(dirty: boolean): void {
    this.editorDirty = dirty;
  }

  onCreated(note: IKBNote | null): void {
    this.creating.set(null);
    if (note && this.hiddenAfterSave(note)) return;
    if (note) {
      this.snackBar.open(this.translate.instant('knowledgeBase.note.createdDone'), undefined, { duration: 3000 });
      this.go(note.slug);
    }
  }

  onEdited(note: IKBNote | null): void {
    this.mode.set('view');
    if (note && this.hiddenAfterSave(note)) return;
    if (note) this.snackBar.open(this.translate.instant('knowledgeBase.note.saved'), undefined, { duration: 3000 });
  }

  /**
   * A note just hidden on a device in family mode: saved, and from now on hidden, so
   * the page goes back to the list and says why .
   */
  private hiddenAfterSave(note: IKBNote): boolean {
    if (!note.hidden || !this.familyMode.active) return false;
    this.snackBar.open(this.translate.instant('hide.noteSavedHidden'), undefined, { duration: 5000 });
    this.store.open(null);
    this.store.loadList();
    this.go();
    return true;
  }

  /** After a conflict the changes were dropped: show the note as it is now. */
  onDiscarded(): void {
    this.mode.set('view');
    const slug = this.store.slug();
    if (slug) this.store.open(slug);
  }

  openExisting(slug: string): void {
    this.editorDirty = false;
    this.select(slug);
  }

  async archive(note: IKBNote): Promise<void> {
    try {
      await this.store.archive(note.slug);
      this.snackBar.open(this.translate.instant('knowledgeBase.note.archivedDone'),
        this.translate.instant('knowledgeBase.note.undo'), { duration: 5000 })
        .onAction().subscribe(() => this.restore(note, false));
    } catch (error) {
      this.showError(error);
    }
  }

  async restore(note: IKBNote, announce = true): Promise<void> {
    try {
      await this.store.restore(note.slug);
      if (announce) this.snackBar.open(this.translate.instant('knowledgeBase.note.restoredDone'), undefined, { duration: 3000 });
    } catch (error) {
      this.showError(error);
    }
  }

  /** Take a file away from the note that keeps it, after asking: it can't be brought back. */
  async removeFile(note: IKBNote, file: IKBFile): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('knowledgeBase.note.removeFileTitle'),
      message: this.translate.instant('knowledgeBase.note.removeFileMessage', { name: file.name }),
      confirmLabel: this.translate.instant('knowledgeBase.note.removeFileConfirm'),
      danger: true
    };
    if (!(await confirmDialog(this.dialog, data))) return;
    try {
      await this.store.removeFile(note.slug, file.name);
      this.snackBar.open(this.translate.instant('knowledgeBase.note.removeFileDone'), undefined, { duration: 3000 });
    } catch (error) {
      this.showError(error);
    }
  }

  async delete(note: IKBNote): Promise<void> {
    const memory = this.store.isMemory(note.slug);
    const data: ConfirmDialogData = memory ? {
      title: this.translate.instant('knowledgeBase.memory.deleteTitle'),
      message: this.translate.instant('knowledgeBase.memory.deleteMessage'),
      confirmLabel: this.translate.instant('knowledgeBase.memory.deleteConfirm'),
      danger: true
    } : {
      title: this.translate.instant('knowledgeBase.note.deleteTitle'),
      message: this.translate.instant('knowledgeBase.note.deleteMessage', { title: note.title }),
      confirmLabel: this.translate.instant('knowledgeBase.note.deleteConfirm'),
      danger: true
    };
    if (!(await confirmDialog(this.dialog, data))) return;
    try {
      await this.store.delete(note.slug);
      this.snackBar.open(this.translate.instant(memory ? 'knowledgeBase.memory.deletedDone' : 'knowledgeBase.note.deletedDone'),
        undefined, { duration: 3000 });
      this.go();
    } catch (error) {
      this.showError(error);
    }
  }

  openConversation(id: string): void {
    this.chatState.loadConversation(id);
    this.router.navigate(['/']);
  }

  async exportVault(): Promise<void> {
    if (this.exporting()) return;
    this.exporting.set(true);
    try {
      const blob = await this.store.exportVault();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const today = new Date();
      const day = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      const agent = this.store.vault() ? `-${slugify(this.store.currentVault()?.personaName ?? '') || 'agent'}` : '';
      link.download = `knowledge-base${agent}-${day}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      this.snackBar.open(this.translate.instant('knowledgeBase.exportFailed', { error: describeHttpError(error, this.translate) }),
        undefined, { duration: 6000 });
    } finally {
      this.exporting.set(false);
    }
  }

  private showError(error: unknown): void {
    const message = kbErrorDetail(error)?.message ?? describeHttpError(error, this.translate);
    this.snackBar.open(this.translate.instant('knowledgeBase.note.failed', { error: message }), undefined, { duration: 6000 });
  }

  /** May the pane switch away from the editor? Asks first if it has unsaved changes. */
  private async leaveEditor(): Promise<boolean> {
    if (!this.editorDirty) return true;
    const data: ConfirmDialogData = {
      title: this.translate.instant('knowledgeBase.editor.discardTitle'),
      message: this.translate.instant('knowledgeBase.editor.discardMessage'),
      confirmLabel: this.translate.instant('knowledgeBase.editor.discardConfirm'),
      danger: true
    };
    const confirmed = await confirmDialog(this.dialog, data);
    if (confirmed) this.editorDirty = false;
    return confirmed;
  }
}

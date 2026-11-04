import { Component, DestroyRef, OnInit, computed, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS, MatFormFieldDefaultOptions, MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IKBNote, IKBNoteSummary, IKBSearchHit, NoteStatus } from '../data/models/knowledge-base.model';
import { ChatStateService } from '../services/chat-state.service';
import { ConfirmDialogData } from '../catalog-admin/confirm-dialog.component';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { KnowledgeBaseStore, kbErrorDetail } from './knowledge-base.store';
import { NoteViewComponent } from './note-view.component';
import { NoteEditorComponent } from './note-editor.component';
import { NoteHistoryComponent } from './note-history.component';
import { formatDate } from './kb-labels';
import { confirmDialog } from './kb-confirm';
import { NOTE_ROUTE, plainText } from './kb-markdown';

type PaneMode = 'view' | 'edit' | 'history';

/**
 * The Knowledge base page (route /knowledge-base, loaded on demand), for signed-in users: the
 * notes their agents keep, to read, search, correct, archive, delete and export for Obsidian.
 * On wide screens the list and the open note sit side by side; on phones they take turns.
 */
@Component({
  selector: 'app-knowledge-base',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
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
    private destroyRef: DestroyRef
  ) {}

  ngOnInit(): void {
    this.store.loadList();
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.creating.set(null);
      this.mode.set('view');
      this.editorDirty = false;
      this.store.open(params.get('slug'));
    });
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
    if (window.matchMedia('(max-width: 768px)').matches) this.router.navigate([NOTE_ROUTE]);
  }

  snippet(item: IKBNoteSummary | IKBSearchHit): string | null {
    return 'snippet' in item ? plainText(item.snippet) : null;
  }

  date(value: string | null): string {
    return formatDate(value, this.translate);
  }

  async select(slug: string): Promise<void> {
    if (!(await this.leaveEditor())) return;
    this.creating.set(null);
    this.mode.set('view');
    this.router.navigate([NOTE_ROUTE, slug]);
  }

  async newNote(title = ''): Promise<void> {
    if (!(await this.leaveEditor())) return;
    this.creating.set({ title });
  }

  backToList(): void {
    this.router.navigate([NOTE_ROUTE]);
  }

  // The note pane

  onDirtyChange(dirty: boolean): void {
    this.editorDirty = dirty;
  }

  onCreated(note: IKBNote | null): void {
    this.creating.set(null);
    if (note) {
      this.snackBar.open(this.translate.instant('knowledgeBase.note.createdDone'), undefined, { duration: 3000 });
      this.router.navigate([NOTE_ROUTE, note.slug]);
    }
  }

  onEdited(note: IKBNote | null): void {
    this.mode.set('view');
    if (note) this.snackBar.open(this.translate.instant('knowledgeBase.note.saved'), undefined, { duration: 3000 });
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

  async delete(note: IKBNote): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('knowledgeBase.note.deleteTitle'),
      message: this.translate.instant('knowledgeBase.note.deleteMessage', { title: note.title }),
      confirmLabel: this.translate.instant('knowledgeBase.note.deleteConfirm'),
      danger: true
    };
    if (!(await confirmDialog(this.dialog, data))) return;
    try {
      await this.store.delete(note.slug);
      this.snackBar.open(this.translate.instant('knowledgeBase.note.deletedDone'), undefined, { duration: 3000 });
      this.router.navigate([NOTE_ROUTE]);
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
      link.download = `knowledge-base-${day}.zip`;
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

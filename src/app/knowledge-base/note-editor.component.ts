import { Component, OnInit, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { COMMA, ENTER } from '@angular/cdk/keycodes';
import { TextFieldModule } from '@angular/cdk/text-field';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatChipInputEvent, MatChipsModule } from '@angular/material/chips';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  IKBNote,
  IKBNoteWrite,
  KB_MAX_CONTENT_CHARS,
  KB_MAX_DESCRIPTION_CHARS,
  KB_MAX_TAG_CHARS,
  KB_MAX_TAGS,
  KB_MAX_TITLE_CHARS,
  NoteStatus
} from '../data/models/knowledge-base.model';
import { ConfirmDialogData } from '../catalog-admin/confirm-dialog.component';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { KnowledgeBaseStore, kbErrorDetail } from './knowledge-base.store';
import { NoteContentComponent } from './note-content.component';
import { slugify } from './kb-markdown';
import { confirmDialog } from './kb-confirm';

/** A tag as the backend stores it: lowercase, without '#', spaces as dashes. */
function normalizeTag(value: string): string {
  return value.trim().replace(/^#+/, '').trim().toLowerCase().replace(/\s+/g, '-');
}

/**
 * Edit a note, or write a new one. Saving sends the version the edit started from: if an agent
 * changed the note meanwhile, the editor says so and offers to save anyway (the other version
 * stays in the history) or to discard the changes.
 */
@Component({
  selector: 'app-note-editor',
  standalone: true,
  imports: [
    FormsModule,
    TextFieldModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    TranslateModule,
    NoteContentComponent
  ],
  templateUrl: './note-editor.component.html',
  styleUrls: ['./kb-pane.scss', './note-editor.component.scss']
})
export class NoteEditorComponent implements OnInit {
  /** The note to edit; null for a new one. */
  readonly note = input<IKBNote | null>(null);
  /** The title of a new note (e.g. from a link to a note that doesn't exist yet). */
  readonly initialTitle = input('');

  /** Done: the saved note, or null when cancelled. */
  readonly done = output<IKBNote | null>();
  /** Discarded after a conflict: show the note as it is now. */
  readonly discarded = output<void>();
  readonly dirtyChange = output<boolean>();
  /** Open an existing note (after "exists already"). */
  readonly openNote = output<string>();

  readonly maxTitle = KB_MAX_TITLE_CHARS;
  readonly maxDescription = KB_MAX_DESCRIPTION_CHARS;
  readonly maxContent = KB_MAX_CONTENT_CHARS;
  readonly separators = [ENTER, COMMA] as const;

  title = '';
  description = '';
  tags: string[] = [];
  content = '';
  view: 'write' | 'preview' = 'write';

  saving = false;
  error: string | null = null;
  tagError: string | null = null;
  conflictVersion: number | null = null;
  existing: { slug: string; status: NoteStatus } | null = null;

  private original = '';
  private dirty = false;

  constructor(
    private store: KnowledgeBaseStore,
    private dialog: MatDialog,
    private translate: TranslateService
  ) {}

  ngOnInit(): void {
    const note = this.note();
    this.title = note?.title ?? this.initialTitle();
    this.description = note?.description ?? '';
    this.tags = [...(note?.tags ?? [])];
    this.content = note?.content ?? '';
    this.original = this.snapshot();
  }

  get isNew(): boolean {
    return this.note() === null;
  }

  /** The slug a new note gets from its title. */
  get newSlug(): string {
    return slugify(this.title) || 'note-…';
  }

  get valid(): boolean {
    return this.title.trim().length > 0 && this.content.trim().length > 0 && this.content.length <= this.maxContent;
  }

  private snapshot(): string {
    return JSON.stringify([this.title, this.description, this.tags, this.content]);
  }

  changed(): void {
    const dirty = this.snapshot() !== this.original;
    if (dirty !== this.dirty) {
      this.dirty = dirty;
      this.dirtyChange.emit(dirty);
    }
  }

  addTag(event: MatChipInputEvent): void {
    const tag = normalizeTag(event.value ?? '');
    event.chipInput.clear();
    this.tagError = null;
    if (!tag || this.tags.includes(tag)) return;
    if (tag.length > KB_MAX_TAG_CHARS) {
      this.tagError = this.translate.instant('knowledgeBase.editor.tagTooLong', { max: KB_MAX_TAG_CHARS });
      return;
    }
    if (this.tags.length >= KB_MAX_TAGS) {
      this.tagError = this.translate.instant('knowledgeBase.editor.tooManyTags', { max: KB_MAX_TAGS });
      return;
    }
    this.tags = [...this.tags, tag];
    this.changed();
  }

  removeTag(tag: string): void {
    this.tags = this.tags.filter(t => t !== tag);
    this.tagError = null;
    this.changed();
  }

  onKeydown(event: KeyboardEvent): void {
    // Ctrl+S / Cmd+S saves
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      this.save();
    }
  }

  async save(baseVersion: number | null = this.note()?.version ?? null): Promise<void> {
    if (!this.valid || this.saving) return;
    this.saving = true;
    this.error = null;
    this.existing = null;
    const write: IKBNoteWrite = {
      title: this.title.trim(),
      content: this.content,
      description: this.description.trim() || null,
      tags: this.tags
    };
    try {
      const note = this.note();
      const saved = note
        ? await this.store.save(note.slug, { ...write, baseVersion })
        : await this.store.create(write);
      this.conflictVersion = null;
      this.dirty = false;
      this.dirtyChange.emit(false);
      this.done.emit(saved);
    } catch (error) {
      const detail = kbErrorDetail(error);
      if (detail?.code === 'conflict' && typeof detail.version === 'number') {
        this.conflictVersion = detail.version;
      } else if (detail?.code === 'exists' && detail.slug) {
        this.existing = { slug: detail.slug, status: detail.status ?? 'active' };
      } else {
        this.error = detail?.message ?? describeHttpError(error, this.translate);
      }
    } finally {
      this.saving = false;
    }
  }

  /** After a conflict: save on top of the version that is there now. */
  saveAnyway(): void {
    const version = this.conflictVersion;
    this.conflictVersion = null;
    this.save(version);
  }

  /** After a conflict: drop the changes and show the note as it is now. */
  discard(): void {
    this.dirty = false;
    this.dirtyChange.emit(false);
    this.discarded.emit();
  }

  async cancel(): Promise<void> {
    if (this.dirty && !(await this.confirmDiscard())) return;
    this.dirty = false;
    this.dirtyChange.emit(false);
    this.done.emit(null);
  }

  private async confirmDiscard(): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('knowledgeBase.editor.discardTitle'),
      message: this.translate.instant('knowledgeBase.editor.discardMessage'),
      confirmLabel: this.translate.instant('knowledgeBase.editor.discardConfirm'),
      danger: true
    };
    return confirmDialog(this.dialog, data);
  }
}

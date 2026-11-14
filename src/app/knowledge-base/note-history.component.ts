import { Component, ElementRef, OnInit, computed, input, output, signal, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IKBNote, IKBRevision, IKBRevisionSummary, RevisionAction } from '../data/models/knowledge-base.model';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { KnowledgeBaseStore, kbErrorDetail } from './knowledge-base.store';
import { NoteContentComponent } from './note-content.component';
import { REVISION_ICONS, actionLabel, authorLabel, formatDateTime } from './kb-labels';

/**
 * The versions of a note, newest first: who wrote each (you, or which agent in which chat), and
 * any of them in full. Restoring a version makes it the current one as a new version, so the
 * history never loses anything.
 */
@Component({
  selector: 'app-note-history',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, MatProgressSpinnerModule, TranslateModule, NoteContentComponent],
  templateUrl: './note-history.component.html',
  styleUrls: ['./kb-pane.scss', './note-history.component.scss']
})
export class NoteHistoryComponent implements OnInit {
  readonly note = input.required<IKBNote>();
  readonly back = output<void>();
  readonly conversation = output<string>();

  /** The files a version's text can place: the ones the note keeps now, and other notes' that it names. */
  readonly files = computed(() => [...(this.note().files ?? []), ...(this.note().placedFiles ?? [])]);

  readonly selectedId = signal<number | null>(null);
  readonly revision = signal<IKBRevision | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly restoring = signal(false);

  private readonly preview = viewChild<ElementRef<HTMLElement>>('preview');
  private request = 0;

  constructor(
    private store: KnowledgeBaseStore,
    private snackBar: MatSnackBar,
    private translate: TranslateService
  ) {}

  ngOnInit(): void {
    const newest = this.note().revisions[0];
    if (newest) this.select(newest);
  }

  isCurrent(revision: IKBRevisionSummary): boolean {
    return revision.id === this.note().version;
  }

  icon(action: RevisionAction): string {
    return REVISION_ICONS[action] ?? 'edit_note';
  }

  label(revision: IKBRevisionSummary): string {
    // A no-break space before the "·": a line never starts with it
    return `${actionLabel(revision.action, this.translate)}\u00a0· ${authorLabel(revision, this.translate)}`;
  }

  date(value: string | null): string {
    return formatDateTime(value, this.translate);
  }

  /** A version picked in the list. Where the list and the version are stacked (phones), the version scrolls into view. */
  pick(revision: IKBRevisionSummary): void {
    this.select(revision);
    if (window.matchMedia('(max-width: 1100px)').matches) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.preview()?.nativeElement.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    }
  }

  async select(revision: IKBRevisionSummary): Promise<void> {
    const request = ++this.request;
    this.selectedId.set(revision.id);
    this.loading.set(true);
    this.error.set(null);
    try {
      const full = await this.store.getRevision(this.note().slug, revision.id);
      if (request !== this.request) return;
      this.revision.set(full);
    } catch (error) {
      if (request !== this.request) return;
      this.revision.set(null);
      this.error.set(describeHttpError(error, this.translate));
    } finally {
      if (request === this.request) this.loading.set(false);
    }
  }

  async restoreSelected(): Promise<void> {
    const revision = this.revision();
    if (!revision || this.restoring()) return;
    this.restoring.set(true);
    try {
      await this.store.restoreRevision(this.note().slug, revision.id, this.note().version);
      this.snackBar.open(this.translate.instant('knowledgeBase.history.restored'), undefined, { duration: 3000 });
      this.back.emit();
    } catch (error) {
      const detail = kbErrorDetail(error);
      if (detail?.code === 'conflict') {
        // The note changed meanwhile: show its new history
        this.snackBar.open(this.translate.instant('knowledgeBase.history.changedMeanwhile'), undefined, { duration: 5000 });
        await this.store.open(this.note().slug);
      } else {
        this.snackBar.open(this.translate.instant('knowledgeBase.note.failed', {
          error: detail?.message ?? describeHttpError(error, this.translate)
        }), undefined, { duration: 6000 });
      }
    } finally {
      this.restoring.set(false);
    }
  }
}

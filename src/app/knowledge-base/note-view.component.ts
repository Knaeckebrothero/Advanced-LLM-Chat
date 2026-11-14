import { Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IKBFile, IKBNote, KB_MEMORY_SLUG } from '../data/models/knowledge-base.model';
import { FilePreviewUtil } from '../data/objects/message';
import { FileTileComponent } from '../components/file-tile/file-tile.component';
import { NoteContentComponent } from './note-content.component';
import { actionLabel, authorLabel, formatDate, formatDateTime } from './kb-labels';
import { NOTE_ROUTE } from './kb-markdown';

/**
 * A note as it reads: title, tags, who changed it last, the content with the files it places, its
 * links both ways, and the files it keeps (each can be taken away from it).
 */
@Component({
  selector: 'app-note-view',
  standalone: true,
  imports: [RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule, TranslateModule, NoteContentComponent,
    FileTileComponent],
  templateUrl: './note-view.component.html',
  styleUrls: ['./kb-pane.scss', './note-view.component.scss']
})
export class NoteViewComponent {
  readonly note = input.required<IKBNote>();

  readonly back = output<void>();
  readonly edit = output<void>();
  readonly history = output<void>();
  readonly archive = output<void>();
  readonly restore = output<void>();
  readonly delete = output<void>();
  readonly tagPicked = output<string>();
  readonly missingLink = output<{ slug: string; text: string }>();
  readonly conversation = output<string>();
  /** Take a file away from the note. */
  readonly removeFile = output<IKBFile>();

  readonly noteRoute = NOTE_ROUTE;

  /** The newest version: who changed the note last, when and where. */
  readonly latest = computed(() => this.note().revisions[0] ?? null);
  /** The agent's memory, which can't be archived (links stay in the knowledge base shown) */
  readonly isMemory = computed(() => this.note().slug === KB_MEMORY_SLUG);
  /** The files the note keeps. */
  readonly kept = computed(() => this.note().files ?? []);
  /** The files its text can place: its own, and the ones of other notes that it names. */
  readonly placeable = computed(() => [...this.kept(), ...(this.note().placedFiles ?? [])]);
  /** The images among the files it keeps: the preview steps through them. */
  readonly keptImages = computed(() => this.kept().filter(file => file.mimeType.startsWith('image/')));

  constructor(private translate: TranslateService) {}

  lastChange(): string {
    const revision = this.latest();
    if (!revision) return '';
    return this.translate.instant('knowledgeBase.note.lastChange', {
      action: actionLabel(revision.action, this.translate),
      date: formatDateTime(revision.createdAt, this.translate),
      who: authorLabel(revision, this.translate)
    });
  }

  /** A kept file's size and, for an image, its pixels: "1024 × 1536 px · 2.1 MB". */
  fileFacts(file: IKBFile): string {
    const facts = [];
    if (file.width && file.height) facts.push(`${file.width} × ${file.height} px`);
    if (file.size) facts.push(FilePreviewUtil.formatFileSize(file.size));
    return facts.join(' · ');
  }

  created(): string {
    return this.translate.instant('knowledgeBase.note.created', { date: formatDate(this.note().createdAt, this.translate) });
  }
}

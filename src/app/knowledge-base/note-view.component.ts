import { Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IKBNote } from '../data/models/knowledge-base.model';
import { NoteContentComponent } from './note-content.component';
import { actionLabel, authorLabel, formatDate, formatDateTime } from './kb-labels';
import { NOTE_ROUTE } from './kb-markdown';

/** A note as it reads: title, tags, who changed it last, the content, and its links both ways. */
@Component({
  selector: 'app-note-view',
  standalone: true,
  imports: [RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatTooltipModule, TranslateModule, NoteContentComponent],
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

  readonly noteRoute = NOTE_ROUTE;

  /** The newest version: who changed the note last, when and where. */
  readonly latest = computed(() => this.note().revisions[0] ?? null);

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

  created(): string {
    return this.translate.instant('knowledgeBase.note.created', { date: formatDate(this.note().createdAt, this.translate) });
  }
}

import { Component, ElementRef, computed, input, output } from '@angular/core';
import { Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { MarkdownComponent } from 'ngx-markdown';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IFileRef } from '../data/models/file.model';
import { IKBLink } from '../data/models/knowledge-base.model';
import { FILE_LINK, answerParts, findFile } from '../chat-ui/chat-ui-message/answer-parts';
import { FileTileComponent } from '../components/file-tile/file-tile.component';
import { openFilePreview } from '../components/file-preview-dialog/file-preview-dialog.component';
import { NOTE_ROUTE, noteMarkdown, noteSlugFromHref } from './kb-markdown';

/**
 * A note's Markdown, rendered. Links to other notes open them on the page; with `links` (the note's
 * links from the API) a link to a note that doesn't exist yet looks different and asks to write it.
 * Web links open in a new tab.
 *
 * The files the text places (![[red-fox.png]] or ![a fox](red-fox.png), docs/knowledge_base.md,
 * "Files") are shown at their place, as in a chat answer: an image as the picture, any other file
 * as a card. A click opens it in the preview, which steps through the note's images.
 */
@Component({
  selector: 'app-note-content',
  standalone: true,
  imports: [MarkdownComponent, FileTileComponent, TranslateModule],
  template: `
    @for (part of parts(); track $index) {
      @if (part.type === 'text') {
        <markdown class="note-markdown" [data]="part.text" (ready)="decorate()" (click)="onClick($event)"></markdown>
      } @else {
        <div class="note-files" [class.is-single]="part.items.length === 1" role="group"
             [attr.aria-label]="'files.shown' | translate">
          @for (item of part.items; track $index) {
            @if (item.file; as file) {
              <app-file-tile [file]="file" [label]="item.label" size="large" [gallery]="gallery()"></app-file-tile>
            }
          }
        </div>
      }
    }
  `,
  styleUrls: ['./note-content.component.scss']
})
export class NoteContentComponent {
  readonly content = input('');
  /** The note's links, to mark links to missing and archived notes (none: no marks). */
  readonly links = input<IKBLink[] | null>(null);
  /** The slug of the note itself (a link to it isn't missing). */
  readonly slug = input<string | null>(null);
  /** False: links to notes do nothing (the editor's preview). */
  readonly interactive = input(true);
  /** The files the text can place, by their names in the knowledge base: the note's own and other notes'. */
  readonly files = input<IFileRef[]>([]);
  /** A link to a note that doesn't exist yet was clicked: its slug and text. */
  readonly missingLink = output<{ slug: string; text: string }>();

  /** The text as parts: Markdown, and the files placed in it. */
  readonly parts = computed(() => {
    const files = this.files();
    const parts = answerParts(
      this.content(),
      // All the files a note can place are known: a name that isn't among them names no file
      reference => findFile(reference, files, [], 0),
      false,
      name => this.translate.instant('files.notFound', { name: '`' + name.replace(/`/g, '') + '`' })
    );
    for (const part of parts) {
      if (part.type === 'text') part.text = noteMarkdown(part.text);
    }
    return parts;
  });

  /** The images the text places, in their order: the preview steps through them. */
  readonly gallery = computed(() => {
    const images = new Map<string, IFileRef>();
    for (const part of this.parts()) {
      for (const item of part.items) {
        if (item.file?.mimeType.startsWith('image/')) images.set(item.file.fileId, item.file);
      }
    }
    return [...images.values()];
  });

  constructor(
    private host: ElementRef<HTMLElement>,
    private router: Router,
    private translate: TranslateService,
    private dialog: MatDialog
  ) {}

  /** Mark the links once the Markdown is rendered. */
  decorate(): void {
    const links = this.links();
    const known = new Map((links ?? []).map(link => [link.slug, link]));
    this.host.nativeElement.querySelectorAll<HTMLAnchorElement>('a[href]').forEach(anchor => {
      const href = anchor.getAttribute('href');
      if (href?.startsWith(FILE_LINK)) return;  // A file placed in a table: opens in the preview
      const slug = noteSlugFromHref(href);
      if (!slug) {
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
        return;
      }
      anchor.classList.add('note-link');
      if (!links || slug === this.slug()) return;
      const link = known.get(slug);
      if (!link || link.title === null) {
        anchor.classList.add('note-link--missing');
        anchor.title = this.translate.instant('knowledgeBase.note.missing');
        return;
      }
      // A bare [[slug]] reads as the note's title, as in the lists of links (the target stays the slug)
      if ((anchor.textContent ?? '').trim() === slug && anchor.childElementCount === 0) {
        anchor.textContent = link.title;
      }
      if (link.status === 'archived') {
        anchor.classList.add('note-link--archived');
        anchor.title = this.translate.instant('knowledgeBase.note.archivedLink');
      }
    });
  }

  onClick(event: MouseEvent): void {
    const anchor = (event.target as HTMLElement | null)?.closest('a');
    const href = anchor?.getAttribute('href') ?? '';
    if (href.startsWith(FILE_LINK)) {
      event.preventDefault();
      const file = this.files().find(known => known.fileId === href.slice(FILE_LINK.length));
      if (file) openFilePreview(this.dialog, file, this.gallery());
      return;
    }
    const slug = noteSlugFromHref(href || null);
    if (!anchor || !slug) return;
    event.preventDefault();
    if (!this.interactive()) return;
    if (anchor.classList.contains('note-link--missing')) {
      this.missingLink.emit({ slug, text: (anchor.textContent ?? '').trim() || slug });
    } else {
      this.router.navigate([NOTE_ROUTE, slug], { queryParamsHandling: 'preserve' });  // In the same knowledge base
    }
  }
}

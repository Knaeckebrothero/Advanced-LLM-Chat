import { Component, ElementRef, computed, input, output } from '@angular/core';
import { Router } from '@angular/router';
import { MarkdownComponent } from 'ngx-markdown';
import { TranslateService } from '@ngx-translate/core';
import { IKBLink } from '../data/models/knowledge-base.model';
import { NOTE_ROUTE, noteMarkdown, noteSlugFromHref } from './kb-markdown';

/**
 * A note's Markdown, rendered. Links to other notes open them on the page; with `links` (the note's
 * links from the API) a link to a note that doesn't exist yet looks different and asks to write it.
 * Web links open in a new tab.
 */
@Component({
  selector: 'app-note-content',
  standalone: true,
  imports: [MarkdownComponent],
  template: `<markdown class="note-markdown" [data]="markdown()" (ready)="decorate()" (click)="onClick($event)"></markdown>`,
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
  /** A link to a note that doesn't exist yet was clicked: its slug and text. */
  readonly missingLink = output<{ slug: string; text: string }>();

  readonly markdown = computed(() => noteMarkdown(this.content()));

  constructor(
    private host: ElementRef<HTMLElement>,
    private router: Router,
    private translate: TranslateService
  ) {}

  /** Mark the links once the Markdown is rendered. */
  decorate(): void {
    const links = this.links();
    const known = new Map((links ?? []).map(link => [link.slug, link]));
    this.host.nativeElement.querySelectorAll<HTMLAnchorElement>('a[href]').forEach(anchor => {
      const slug = noteSlugFromHref(anchor.getAttribute('href'));
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
    const slug = noteSlugFromHref(anchor?.getAttribute('href') ?? null);
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

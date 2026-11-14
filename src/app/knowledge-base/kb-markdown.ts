/**
 * Links between notes on the Knowledge base page. Notes link to each other with [[slug]], [[Title]],
 * [[slug|text]], [[slug#heading]] or Markdown links to slug.md; the backend turns each target into a
 * slug the same way as slugify() here (backend/services/knowledge_base.py).
 */

/** Where a note opens: /knowledge-base/<slug> */
export const NOTE_ROUTE = '/knowledge-base';

const MAX_SLUG_CHARS = 80;
const TRANSLITERATION: Record<string, string> = { 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'æ': 'ae', 'ø': 'o', 'œ': 'oe' };

// [[target]], [[target#heading]], [[target|text]]
const WIKILINK_RE = /\[\[([^[\]|#]+)(#[^[\]|]*)?(?:\|([^[\]]*))?\]\]/g;
// [text](target "title") whose target is a note: no scheme, ends in .md (before an #anchor)
const MD_LINK_RE = /(\[[^[\]]*\]\(\s*<?)([^)\s>]+)(>?(?:\s+"[^"]*")?\s*\))/g;
// Task list items: "- [ ] open", "- [x] done"
const TASK_RE = /^(\s*(?:[-*+]|\d+[.)])\s+)\[([ xX])\](?=\s)/gm;
// Code is left as it is: fenced blocks and inline code
export const CODE_RE = /(```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`)/;

/** A slug for a title or link target: lowercase ASCII letters, digits and dashes ("Größe & Gewicht" -> "groesse-gewicht"). */
export function slugify(value: string): string {
  let text = value.toLowerCase().replace(/[äöüßæøœ]/g, c => TRANSLITERATION[c] ?? c);
  text = text.normalize('NFKD').replace(/[^\x00-\x7f]/g, '');
  text = text.replace(/[^a-z0-9\s_-]/g, ' ').replace(/[\s_-]+/g, '-').replace(/^-+|-+$/g, '');
  return text.slice(0, MAX_SLUG_CHARS).replace(/-+$/, '');
}

/** The note a link's href points to, or null for other links. */
export function noteSlugFromHref(href: string | null): string | null {
  const prefix = NOTE_ROUTE + '/';
  if (!href || !href.startsWith(prefix)) return null;
  return decodeURIComponent(href.slice(prefix.length).split(/[?#]/)[0]) || null;
}

/** The slug a Markdown link target points to (other-note.md, folder/Other%20Note.md#part), or null. */
function markdownLinkSlug(target: string): string | null {
  if (target.includes(':') || target.startsWith('#')) return null;
  let name = target.split('#')[0].replace(/\/+$/, '').split('/').pop() ?? '';
  try {
    name = decodeURIComponent(name);
  } catch {
    // Keep the name as it is
  }
  if (!name.toLowerCase().endsWith('.md')) return null;
  return slugify(name.slice(0, -3)) || null;
}

/**
 * Markdown as plain text for a search result's passage: links show their text, emphasis, code
 * marks and heading marks go (the passage may start or end inside them).
 */
export function plainText(markdown: string): string {
  return markdown
    // A file the note places says nothing in a line of text: ![[red-fox.png]]
    .replace(/!\[\[[^[\]\n]*\]\]/g, ' ')
    .replace(WIKILINK_RE, (_whole, target: string, _heading: string | undefined, text: string | undefined) => (text ?? target).trim())
    .replace(/!?\[([^[\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[\[|\]\]/g, '')
    .replace(/\*+|~~|`+/g, '')
    .replace(/(^|\s)#{1,6}\s/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Escape text for the text of a Markdown link. */
function linkText(text: string): string {
  return text.replace(/([\\[\]])/g, '\\$1');
}

/**
 * A note's Markdown with its links to other notes as links to their page (outside of code), so
 * the Markdown renderer shows them as links. Task boxes become ☐ and ☑: the sanitizer removes the
 * checkboxes the renderer would make.
 */
export function noteMarkdown(content: string): string {
  return content
    .split(CODE_RE)
    .map((part, index) => {
      if (index % 2 === 1) return part;  // Code
      return part
        .replace(WIKILINK_RE, (whole, target: string, _heading: string | undefined, text: string | undefined) => {
          const slug = slugify(target);
          if (!slug) return whole;
          const label = (text ?? target).trim() || slug;
          return `[${linkText(label)}](${NOTE_ROUTE}/${slug})`;
        })
        .replace(MD_LINK_RE, (whole, start: string, target: string, end: string) => {
          const slug = markdownLinkSlug(target);
          return slug ? `${start}${NOTE_ROUTE}/${slug}${end}` : whole;
        })
        .replace(TASK_RE, (_whole, start: string, mark: string) => `${start}${mark === ' ' ? '☐' : '☑'}`);
    })
    .join('');
}

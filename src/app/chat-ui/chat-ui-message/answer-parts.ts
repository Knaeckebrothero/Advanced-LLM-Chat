/**
 * The files an agent places in the text of its answer (docs/files.md, "In the chat").
 *
 * An agent shows a file of the conversation by writing a Markdown image whose address is the
 * file's name or file ID: ![A red fox in the snow](fox-1.png). The chat splits the text there
 * and shows the file itself at that place, between the Markdown before and after it. Obsidian's
 * ![[fox-1.png]] works too. Images at web addresses are never loaded (the page may only load
 * images from the app's own address, and an address a model writes can carry data away): they
 * become links.
 */
import { IFileRef } from '../../data/models/file.model';
import { CODE_RE } from '../../knowledge-base/kb-markdown';

/** A file placed in the text; `file` is null while the conversation's files are still loading. */
export interface PlacedFile {
  reference: string;
  label: string;  // What the agent says it shows (the image's text), may be empty
  file: IFileRef | null;
}

/** A stretch of the answer: Markdown (`text`), or files next to each other (`items`). */
export interface AnswerPart {
  type: 'text' | 'files';
  text: string;
  items: PlacedFile[];
}

/** What a reference names: the file, null for none, undefined while that isn't known yet. */
export type FileFinder = (reference: string) => IFileRef | null | undefined;

/** Where a link to a placed file points (in a table, where the file itself has no room). */
export const FILE_LINK = '#file:';

const FILE_ID_RE = /^file_\d+_[0-9a-f]+$/;
// ![[target]], ![[target|size]] or ![text](address "title"); the address may have spaces and (brackets)
const PLACED_RE = /!\[\[([^[\]|\n]+)(?:\|[^[\]\n]*)?\]\]|!\[((?:[^[\]\\\n]|\\.|\[[^[\]\n]*\])*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)/g;
// The start of one, still being written: hidden until it is complete
const UNFINISHED_RE = /!\[[^\]\n]*(?:\](?:\([^)\n]*)?)?$/;
const WEB_ADDRESS_RE = /^(?:https?:)?\/\//i;
// A line that is nothing but the start of a list item or a quote
const EMPTY_ITEM_RE = /(^|\n)[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]*|(?:>[ \t]*)+)$/;
// What may stand between two files that are shown next to each other: space, commas, list marks
const BETWEEN_FILES_RE = /(?:^|\n)[ \t]*(?:[-*+]|\d+[.)])(?=\s|$)|[\s,;]/g;

/** The time in a stored file's ID (file_<milliseconds>_<hex>); 0 for another ID. */
function fileTime(fileId: string): number {
  return FILE_ID_RE.test(fileId) ? Number(fileId.split('_')[1]) : 0;
}

/** The address of a Markdown image without its "title" and <angle brackets>. */
function address(raw: string): string {
  let target = raw.trim().replace(/\s+(?:"[^"]*"|'[^']*')$/, '').trim();
  if (target.startsWith('<') && target.endsWith('>')) target = target.slice(1, -1).trim();
  return target;
}

/** A reference as a plain file name: sandbox:/mnt/data/My%20Fox.png -> My Fox.png */
function plainName(reference: string): string {
  let name = reference.replace(/^[a-z][a-z0-9+.-]*:/i, '').split(/[?#]/)[0].replace(/\/+$/, '');
  name = name.split('/').pop() ?? '';
  try {
    name = decodeURIComponent(name);
  } catch {
    // Keep the name as it is
  }
  return name.trim();
}

/** The files among `files` that a reference names: by file ID, else by name. */
function matches(files: IFileRef[], reference: string): IFileRef[] {
  if (FILE_ID_RE.test(reference)) return files.filter(file => file.fileId === reference);
  for (const name of new Set([reference, plainName(reference)])) {
    if (!name) continue;
    const exact = files.filter(file => file.name === name);
    if (exact.length) return exact;
    const lower = name.toLowerCase();
    const similar = files.filter(file => file.name.toLowerCase() === lower);
    if (similar.length) return similar;
  }
  return [];
}

/**
 * The file an answer means by a reference (a name or a file ID).
 *
 * @param own The files of the answer itself (what its tools created), which come first.
 * @param conversation The conversation's files, or undefined while they aren't loaded.
 * @param answerTime The answer's time in milliseconds (its message ID): of several files with
 *     the same name, the answer means the newest it could know.
 * @returns The file, null if there is none, undefined if the conversation's files are needed
 *     to tell and aren't loaded.
 */
export function findFile(reference: string, own: IFileRef[], conversation: IFileRef[] | undefined,
                         answerTime: number): IFileRef | null | undefined {
  reference = reference.trim().replace(/^["']|["']$/g, '');
  if (!reference) return null;
  const mine = matches(own, reference);
  if (mine.length) return mine[mine.length - 1];
  if (!conversation) return undefined;
  const found = matches(conversation, reference).sort((a, b) => fileTime(a.fileId) - fileTime(b.fileId));
  if (!found.length) return null;
  const known = found.filter(file => fileTime(file.fileId) <= answerTime);
  return known.length ? known[known.length - 1] : found[0];
}

function escapeLabel(text: string): string {
  return text.replace(/([\\[\]])/g, '\\$1');
}

/**
 * An answer's text as parts: Markdown, and the files placed in it.
 *
 * @param content The answer's text.
 * @param find What a reference names (findFile()).
 * @param streaming The answer is still being written: a reference that isn't complete yet is
 *     held back, so its Markdown doesn't flash up.
 * @param missing The text shown in place of a reference to a file that doesn't exist.
 */
export function answerParts(content: string, find: FileFinder, streaming: boolean,
                            missing: (name: string) => string): AnswerPart[] {
  if (!content.includes('![')) {
    return content ? [{ type: 'text', text: content, items: [] }] : [];
  }
  const parts: AnswerPart[] = [];
  let text = '';

  const endText = (beforeFile: boolean) => {
    // A file stands where its line was: no empty list item or quote stays before it
    let before = beforeFile ? text.replace(EMPTY_ITEM_RE, '$1') : text;
    const last = parts[parts.length - 1];
    if (last?.type === 'files') {
      // After a file the text starts a new block: an indented first line would become code
      before = before.replace(/^[ \t]*\n+/, '').replace(/^[ \t]+/, '');
    }
    if (before.trim()) parts.push({ type: 'text', text: before.replace(/\s+$/, ''), items: [] });
    text = '';
  };

  const place = (item: PlacedFile) => {
    const last = parts[parts.length - 1];
    // Files with nothing between them stand next to each other
    if (last?.type === 'files' && !text.replace(BETWEEN_FILES_RE, '')) {
      text = '';
      last.items.push(item);
      return;
    }
    endText(true);
    parts.push({ type: 'files', text: '', items: [item] });
  };

  const pieces = content.split(CODE_RE);
  pieces.forEach((piece, index) => {
    if (index % 2 === 1) {  // Code stays as it is
      text += piece;
      return;
    }
    if (streaming && index === pieces.length - 1) {
      piece = piece.replace(UNFINISHED_RE, '');
    }
    let position = 0;
    for (const match of piece.matchAll(PLACED_RE)) {
      const start = match.index ?? 0;
      text += piece.slice(position, start);
      position = start + match[0].length;
      const embed = match[1] !== undefined;
      const reference = embed ? match[1].trim() : address(match[3]);
      const label = embed ? '' : match[2].replace(/\\(.)/g, '$1').trim();

      if (!embed && WEB_ADDRESS_RE.test(reference)) {
        // An image somewhere on the web: a link to it
        text += `[${escapeLabel(label || reference)}](<${reference.replace(/[<>]/g, '')}>)`;
        continue;
      }
      if (!embed && /^(?:data|blob):/i.test(reference)) {
        text += match[0];
        continue;
      }
      const file = find(reference);
      if (file === null) {
        // No such file. ![[Some note]] may be a note: without the mark it is a link to it
        text += embed ? match[0].slice(1) : missing(plainName(reference) || reference);
        continue;
      }
      const lineStart = piece.lastIndexOf('\n', start - 1) + 1;
      if (/^[ \t]*\|/.test(piece.slice(lineStart, start))) {
        // In a table the file has no room: a link that opens it (a row can't be split either)
        const name = file?.name ?? plainName(reference);
        text += file ? `[${escapeLabel(label || name)}](${FILE_LINK}${file.fileId})` : escapeLabel(label || name);
        continue;
      }
      place({ reference, label, file: file ?? null });
    }
    text += piece.slice(position);
  });
  endText(false);
  return parts;
}

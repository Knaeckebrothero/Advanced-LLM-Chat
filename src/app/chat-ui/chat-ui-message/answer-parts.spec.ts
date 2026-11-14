import { IFileRef } from '../../data/models/file.model';
import { AnswerPart, FILE_LINK, answerParts, findFile } from './answer-parts';

const fox: IFileRef = { fileId: 'file_2000_aa', name: 'fox-1.png', mimeType: 'image/png', width: 1024, height: 768 };
const wolf: IFileRef = { fileId: 'file_2001_bb', name: 'fox-2.png', mimeType: 'image/png' };
const report: IFileRef = { fileId: 'file_1000_cc', name: 'Report (final) v2.pdf', mimeType: 'application/pdf' };
const photoOld: IFileRef = { fileId: 'file_500_dd', name: 'image.png', mimeType: 'image/png' };
const photoNew: IFileRef = { fileId: 'file_3000_ee', name: 'image.png', mimeType: 'image/png' };

const own = [fox, wolf];
const conversation = [photoOld, report, fox, wolf, photoNew];

function parts(content: string, streaming = false, loaded = true): AnswerPart[] {
  const known = loaded ? conversation : undefined;
  return answerParts(content, reference => findFile(reference, own, known, 2500), streaming, name => `(no ${name})`);
}

/** The parts in short: text as it is, files as <name, name>. */
function short(content: string, streaming = false): string[] {
  return parts(content, streaming).map(part =>
    part.type === 'text' ? part.text : `<${part.items.map(item => item.file?.name ?? '?').join(', ')}>`);
}

describe('answerParts', () => {
  it('leaves an answer without files as one text', () => {
    expect(short('Just **text**.')).toEqual(['Just **text**.']);
    expect(short('')).toEqual([]);
  });

  it('shows a file where the answer places it', () => {
    expect(short('Here it is:\n\n![A red fox](fox-1.png)\n\nDo you like it?'))
      .toEqual(['Here it is:', '<fox-1.png>', 'Do you like it?']);
    const [, files] = parts('Look:\n\n![A red fox](fox-1.png "title")');
    expect(files.items[0]).toEqual({ reference: 'fox-1.png', label: 'A red fox', file: fox });
  });

  it('puts files in a row next to each other', () => {
    expect(short('![a](fox-1.png)\n![b](fox-2.png)\n\nBoth.')).toEqual(['<fox-1.png, fox-2.png>', 'Both.']);
    expect(short('1. ![a](fox-1.png)\n2. ![b](fox-2.png)')).toEqual(['<fox-1.png, fox-2.png>']);
    expect(short('![a](fox-1.png) text ![b](fox-2.png)')).toEqual(['<fox-1.png>', 'text', '<fox-2.png>']);
  });

  it('keeps a list readable around a file', () => {
    expect(short('1. **One** is dark\n   ![a](fox-1.png)\n2. **Two** is light\n   ![b](fox-2.png)\n\n    Which one?'))
      .toEqual(['1. **One** is dark', '<fox-1.png>', '2. **Two** is light', '<fox-2.png>', 'Which one?']);
    expect(short('Intro\n\n- ![a](fox-1.png)')).toEqual(['Intro', '<fox-1.png>']);
  });

  it('finds files by ID, by name whatever its case, with spaces, brackets and other spellings', () => {
    expect(short('![x](file_2001_bb)')).toEqual(['<fox-2.png>']);
    expect(short('![x](FOX-1.PNG)')).toEqual(['<fox-1.png>']);
    expect(short('![the report](Report (final) v2.pdf)')).toEqual(['<Report (final) v2.pdf>']);
    expect(short('![x](<Report (final) v2.pdf>)')).toEqual(['<Report (final) v2.pdf>']);
    expect(short('![x](Report%20(final)%20v2.pdf)')).toEqual(['<Report (final) v2.pdf>']);
    expect(short('![x](sandbox:/mnt/data/fox-1.png)')).toEqual(['<fox-1.png>']);
    expect(short('![[fox-1.png]] and ![[fox-2.png|300]]')).toEqual(['<fox-1.png>', 'and', '<fox-2.png>']);
    expect(short('![Fox [draft]](fox-1.png)')).toEqual(['<fox-1.png>']);
  });

  it('means the newest file of a name that the answer could know', () => {
    expect(findFile('image.png', [], conversation, 2500)).toBe(photoOld);
    expect(findFile('image.png', [], conversation, 3500)).toBe(photoNew);
    expect(findFile('image.png', [], [photoNew], 2500)).toBe(photoNew);
    expect(findFile('fox-1.png', own, undefined, 2500)).toBe(fox);
    expect(findFile('image.png', own, undefined, 2500)).toBeUndefined();
    expect(findFile('nope.png', own, conversation, 2500)).toBeNull();
  });

  it('finds a file that a note of the knowledge base keeps, after the conversation\'s own', () => {
    // Kept under the note's name: the same stored file as fox-1.png, and one of another conversation
    const keptFox: IFileRef = { fileId: 'file_2000_aa', name: 'red-fox.png', mimeType: 'image/png' };
    const keptCat: IFileRef = { fileId: 'file_100_ff', name: 'Luna.jpg', mimeType: 'image/jpeg' };
    const keptImage: IFileRef = { fileId: 'file_200_gg', name: 'image.png', mimeType: 'image/png' };
    const kept = [keptFox, keptCat, keptImage];
    expect(findFile('luna.jpg', own, conversation, 2500, kept)).toBe(keptCat);
    expect(findFile('red-fox.png', [], [], 2500, kept)).toBe(keptFox);
    expect(findFile('image.png', own, conversation, 2500, kept)).toBe(photoOld);  // The conversation's comes first
    expect(findFile('luna.jpg', own, undefined, 2500, kept)).toBeUndefined();     // Not known yet whether it has one
    expect(findFile('nope.png', own, conversation, 2500, kept)).toBeNull();
    // What the answer's knowledge base tools named is among its own files
    expect(findFile('red-fox.png', [...own, keptFox], undefined, 2500)).toBe(keptFox);
    const placed = answerParts('Here: ![[Luna.jpg]]', reference => findFile(reference, own, conversation, 2500, kept),
      false, name => `(no ${name})`);
    expect(placed.map(part => part.type)).toEqual(['text', 'files']);
    expect(placed[1].items[0].file).toBe(keptCat);
  });

  it('says so when a file does not exist, and waits while the files are loading', () => {
    expect(short('See ![x](nope.png) here')).toEqual(['See (no nope.png) here']);
    const waiting = parts('![x](image.png)', false, false);
    expect(waiting[0].items[0].file).toBeNull();
    // An embed that is no file may be a note: it becomes a link to it
    expect(short('![[Some note]]')).toEqual(['[[Some note]]']);
  });

  it('never loads an image from the web: it becomes a link', () => {
    expect(short('![A cat](https://example.com/cat.png?x=1)')).toEqual(['[A cat](<https://example.com/cat.png?x=1>)']);
    expect(short('![](//example.com/cat.png)')).toEqual(['[//example.com/cat.png](<//example.com/cat.png>)']);
    expect(short('![x](data:image/png;base64,AAAA)')).toEqual(['![x](data:image/png;base64,AAAA)']);
  });

  it('leaves code alone', () => {
    const code = 'Write `![alt](fox-1.png)` or:\n\n```md\n![alt](fox-1.png)\n```';
    expect(short(code)).toEqual([code]);
  });

  it('links a file in a table instead of breaking the table', () => {
    const table = '| Draft | Image |\n|---|---|\n| One | ![first](fox-1.png) |\n| Two | ![](fox-2.png) |';
    expect(short(table)).toEqual([
      `| Draft | Image |\n|---|---|\n| One | [first](${FILE_LINK}file_2000_aa) |\n| Two | [fox-2.png](${FILE_LINK}file_2001_bb) |`
    ]);
  });

  it('holds back a reference that is still being written', () => {
    expect(short('Here:\n\n![A red', true)).toEqual(['Here:']);
    expect(short('Here:\n\n![A red fox](fox-1', true)).toEqual(['Here:']);
    expect(short('Here:\n\n![[fox-1.p', true)).toEqual(['Here:']);
    expect(short('Here:\n\n![A red fox](fox-1.png)', true)).toEqual(['Here:', '<fox-1.png>']);
    expect(short('Here:\n\n![A red', false)).toEqual(['Here:\n\n![A red']);
    // A list item that only starts is not taken for the line of a file
    expect(short('![a](fox-1.png)\n\nNext:\n- ', true)).toEqual(['<fox-1.png>', 'Next:\n-']);
  });
});

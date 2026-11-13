import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IChatFile } from '../../data/models/file.model';
import { FilePreviewUtil } from '../../data/objects/message';
import { ApiService } from '../../services/api.service';
import { saveBlob } from '../../utils/download.util';
import { openFilePreview } from '../file-preview-dialog/file-preview-dialog.component';
import { FileTileComponent } from '../file-tile/file-tile.component';

export interface ConversationFilesDialogData {
  /** The conversation whose files are listed; without one, the files of all the user's conversations. */
  conversationId?: string;
  conversationName?: string;
}

/** What the dialog closes with: a conversation picked in the list of all files, to open. */
export interface ConversationFilesDialogResult {
  openConversationId?: string;
}

/** Which files are listed: all, the ones the user attached, or the ones the agent's tools created. */
export type FileSourceFilter = 'all' | 'upload' | 'tool';

// All files are loaded this many at a time
const PAGE_SIZE = 100;

/** A file with the texts shown for it, worked out once when the list arrives. */
interface ListedFile {
  file: IChatFile;
  source: 'upload' | 'tool';
  /** A picture's tooltip and name for screen readers: its name, size and where it comes from. */
  label: string;
  /** A row's second line: size, where the file comes from and when. */
  details: string;
  icon: string;
}

/** The listed files of one conversation: its pictures and everything else, newest first. */
interface FileGroup {
  /** In the list of all files: the conversation, whose name heads the group. */
  conversationId?: string;
  name?: string;
  images: ListedFile[];
  others: ListedFile[];
}

/**
 * The files of a conversation ("Files of this chat"), or of all the user's conversations ("All
 * files", from the settings): what the user attached and what the agents' tools created, newest
 * first (docs/files.md). Images are a gallery whose preview steps from one to the next, any other
 * file is a row; each can be opened and downloaded. All files are grouped by their conversation,
 * which a click on its name opens, and arrive a page at a time.
 */
@Component({
  selector: 'app-conversation-files-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslateModule,
    FileTileComponent
  ],
  templateUrl: './conversation-files-dialog.component.html',
  styleUrls: ['./conversation-files-dialog.component.scss']
})
export class ConversationFilesDialogComponent implements OnInit {
  /** The files of all conversations, not of one. */
  readonly all: boolean;
  state: 'loading' | 'loaded' | 'error' = 'loading';
  readonly filters: FileSourceFilter[] = ['all', 'upload', 'tool'];
  filter: FileSourceFilter = 'all';
  counts: Record<FileSourceFilter, number> = { all: 0, upload: 0, tool: 0 };
  groups: FileGroup[] = [];
  /** The listed pictures in their order, which the preview steps through. */
  gallery: IChatFile[] = [];
  /** How many files there are and what they take together, "14 files · 23.4 MB". */
  summary = '';
  /** All files: how many of them are listed so far. */
  listed = 0;
  loadingMore = false;

  // The files of one conversation, which are filtered here; all files are filtered by the server
  private files: ListedFile[] = [];
  private listedIds = new Set<string>();
  // Counts up with every list asked for: a slower answer to an earlier question is dropped
  private asked = 0;
  // The files being fetched to save them
  private saving = new Set<string>();

  constructor(
    private dialogRef: MatDialogRef<ConversationFilesDialogComponent, ConversationFilesDialogResult>,
    @Inject(MAT_DIALOG_DATA) public data: ConversationFilesDialogData,
    private api: ApiService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
    private translate: TranslateService
  ) {
    this.all = !data.conversationId;
  }

  ngOnInit(): void {
    void this.load();
  }

  /** Load the list from its start. */
  async load(): Promise<void> {
    this.state = 'loading';
    const asked = ++this.asked;
    try {
      if (this.all) {
        await this.loadPage(asked, true);
      } else {
        const files = await this.api.getConversationFiles(this.data.conversationId!);
        if (asked !== this.asked) return;
        this.files = [...files].reverse().map(file => this.listedFile(file));
        const uploads = this.files.filter(entry => entry.source === 'upload').length;
        this.counts = { all: this.files.length, upload: uploads, tool: this.files.length - uploads };
        this.summary = this.describe(files.length, files.reduce((sum, file) => sum + (file.size ?? 0), 0));
        this.showListed();
      }
    } catch (error) {
      if (asked !== this.asked) return;
      console.error('Error loading the files:', error);
      this.state = 'error';
      return;
    }
    if (asked === this.asked) this.state = 'loaded';
  }

  /** All files: the first page (from the start) or the next one, added to the groups. */
  private async loadPage(asked: number, fromStart: boolean): Promise<void> {
    const offset = fromStart ? 0 : this.listed;
    const page = await this.api.getAllFiles(offset, PAGE_SIZE, this.filter === 'all' ? undefined : this.filter);
    if (asked !== this.asked) return;
    if (fromStart) {
      this.groups = [];
      this.gallery = [];
      this.listedIds.clear();
      this.listed = 0;
    }
    this.counts = { all: page.counts.upload + page.counts.tool, upload: page.counts.upload, tool: page.counts.tool };
    this.summary = this.describe(this.counts.all, page.size);
    // Counted by what the server sent, so the next page starts after it
    this.listed += page.files.length;
    const gallery = [...this.gallery];
    for (const file of page.files) {
      // A file stored since the last page moves the others back by one
      if (this.listedIds.has(file.fileId)) continue;
      this.listedIds.add(file.fileId);
      let group = this.groups[this.groups.length - 1];
      if (!group || group.conversationId !== file.conversationId) {
        group = { conversationId: file.conversationId, name: file.conversationName, images: [], others: [] };
        this.groups.push(group);
      }
      this.add(group, this.listedFile(file), gallery);
    }
    // A new list, so the tiles get the pictures added to step through
    this.gallery = gallery;
    // Nothing came although more was expected: the rest is gone, so stop offering it
    if (!page.files.length) this.listed = this.total;
  }

  private add(group: FileGroup, entry: ListedFile, gallery: IChatFile[]): void {
    if (entry.file.mimeType.startsWith('image/')) {
      group.images.push(entry);
      gallery.push(entry.file);
    } else {
      group.others.push(entry);
    }
  }

  /** All files: how many the chosen filter has. */
  get total(): number {
    return this.counts[this.filter];
  }

  /** All files: the next page. */
  async more(): Promise<void> {
    if (this.loadingMore || this.state !== 'loaded') return;
    this.loadingMore = true;
    const asked = this.asked;
    try {
      await this.loadPage(asked, false);
    } catch (error) {
      console.error('Error loading more files:', error);
      if (asked === this.asked) {
        this.snackBar.open(this.translate.instant('files.loadFailed'), undefined, { duration: 5000 });
      }
    } finally {
      this.loadingMore = false;
    }
  }

  /** List the files of one source, or all of them. */
  show(filter: FileSourceFilter): void {
    if (filter === this.filter) return;
    this.filter = filter;
    if (this.all) {
      void this.load();
    } else {
      this.showListed();
    }
  }

  /** One conversation: its files of the chosen source as the one group. */
  private showListed(): void {
    const group: FileGroup = { images: [], others: [] };
    const gallery: IChatFile[] = [];
    for (const entry of this.files) {
      if (this.filter === 'all' || entry.source === this.filter) this.add(group, entry, gallery);
    }
    this.gallery = gallery;
    this.groups = group.images.length || group.others.length ? [group] : [];
  }

  private listedFile(file: IChatFile): ListedFile {
    const source = file.source === 'tool' ? 'tool' : 'upload';
    const size = file.size ? FilePreviewUtil.formatFileSize(file.size) : '';
    const origin = this.origin(file, source);
    return {
      file,
      source,
      label: [file.name, size, origin].filter(Boolean).join(' · '),
      details: [size, origin, this.when(file)].filter(Boolean).join(' · '),
      icon: file.mimeType === 'application/pdf'
        ? 'picture_as_pdf' : FilePreviewUtil.getFileIcon(FilePreviewUtil.getFileType(file.mimeType))
    };
  }

  private describe(count: number, bytes: number): string {
    const files = count === 1
      ? this.translate.instant('files.countOne')
      : this.translate.instant('files.count', { count });
    return bytes ? `${files} · ${FilePreviewUtil.formatFileSize(bytes)}` : files;
  }

  /** Where a file comes from: "Uploaded", or "Created by Civitai: Run step". */
  private origin(file: IChatFile, source: 'upload' | 'tool'): string {
    if (source === 'upload') return this.translate.instant('files.uploaded');
    return file.origin
      ? this.translate.instant('files.createdBy', { origin: file.origin })
      : this.translate.instant('files.createdByAgent');
  }

  private when(file: IChatFile): string {
    const time = file.createdAt ? new Date(file.createdAt) : null;
    if (!time || isNaN(time.getTime())) return '';
    return new Intl.DateTimeFormat(this.translate.currentLang || 'en', { dateStyle: 'medium', timeStyle: 'short' }).format(time);
  }

  open(file: IChatFile): void {
    openFilePreview(this.dialog, file);
  }

  /** Leave the list for the conversation a group of files belongs to. */
  openConversation(group: FileGroup): void {
    if (group.conversationId) this.dialogRef.close({ openConversationId: group.conversationId });
  }

  isSaving(file: IChatFile): boolean {
    return this.saving.has(file.fileId);
  }

  /** Download a file under its name. */
  async save(file: IChatFile): Promise<void> {
    if (this.saving.has(file.fileId)) return;
    this.saving.add(file.fileId);
    try {
      saveBlob(await this.api.getFile(file.fileId), file.name);
    } catch (error) {
      this.snackBar.open(this.translate.instant('files.downloadFailed', { name: file.name }), undefined, { duration: 5000 });
    } finally {
      this.saving.delete(file.fileId);
    }
  }

  close(): void {
    this.dialogRef.close();
  }
}

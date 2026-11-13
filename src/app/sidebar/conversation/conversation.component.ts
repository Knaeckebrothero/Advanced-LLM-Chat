import { Component, EventEmitter, Input, OnInit, Output, ViewChild, OnDestroy, ElementRef } from '@angular/core';
import { Conversation } from '../../data/objects/conversation';
import { Message } from '../../data/objects/message';
import { CommonModule } from '@angular/common';
import { ChatStateService } from "../../services/chat-state.service";
import { FormsModule } from "@angular/forms";
import { firstValueFrom } from 'rxjs';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Router } from '@angular/router';
import { describeHttpError } from '../../catalog-admin/catalog-admin.utils';
import { CatalogService } from '../../services/catalog.service';
import { AuthService } from '../../auth/auth.service';
import { FamilyModeService } from '../../services/family-mode.service';
import { ConversationFilesDialogService } from '../../components/conversation-files/conversation-files-dialog.service';


@Component({
  selector: 'app-conversation',
  standalone: true,
  imports: [CommonModule, FormsModule, MatMenuModule, MatIconModule, MatButtonModule, TranslateModule],
  templateUrl: './conversation.component.html',
  styleUrls: ['./conversation.component.scss']
})
export class ConversationComponent implements OnInit, OnDestroy {
  @Input() conversation!: Conversation;
  @Input() highlighted: boolean = false; // Added Input
  @Output() selected = new EventEmitter<Conversation>();
  @Output() delete = new EventEmitter<string>();
  @ViewChild(MatMenuTrigger) menuTrigger!: MatMenuTrigger;
  @ViewChild('editInput') editInput?: ElementRef<HTMLInputElement>;

  messages: Message[] = [];
  editing = false;
  newName = '';
  private longPressTimer: any;
  private longPressTriggered = false;

  /** The memory review of this conversation runs (reviewMemory()). */
  reviewingMemory = false;

  constructor(
    private chatState: ChatStateService,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private catalog: CatalogService,
    private auth: AuthService,
    private router: Router,
    private familyMode: FamilyModeService,
    private filesDialog: ConversationFilesDialogService
  ) {}

  onSelect(): void {
    // Don't select if long press was triggered
    if (!this.longPressTriggered) {
      this.selected.emit(this.conversation);
    }
    this.longPressTriggered = false;
  }

  onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.delete.emit(this.conversation.id);
  }

  // Lifecycle hook: called once after the component is initialized.
  // Loads messages related to this conversation for preview purposes.
  async ngOnInit() {
    // Messages are now managed by repositories and state services
    // No need to load directly from DB
  }

  // Emits the selected conversation to the parent component when the user clicks on this conversation.
  onClick(): void {
    this.selected.emit(this.conversation);
  }


  startEditing(): void {
    this.editing = true;
    this.newName = this.conversation.name;
    
    // Auto-focus the input field after DOM updates
    setTimeout(() => {
      if (this.editInput) {
        this.editInput.nativeElement.focus();
        this.editInput.nativeElement.select(); // Select all text for easy replacement
      }
    }, 50);
  }

  onMenuClick(event: MouseEvent): void {
    event.stopPropagation();
  }

  onRename(): void {
    this.startEditing();
  }

  onLongPress(): void {
    // Open the dropdown menu programmatically on long press (mobile)
    if (this.menuTrigger) {
      this.longPressTriggered = true;
      this.menuTrigger.openMenu();
    }
  }

  onPressStart(event: MouseEvent | TouchEvent): void {
    // Only handle long press on mobile (screen width < 768px)
    if (window.innerWidth < 768) {
      this.longPressTimer = setTimeout(() => {
        this.onLongPress();
      }, 500); // 500ms for long press
    }
  }

  onPressEnd(): void {
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }
  }

  async finishEditing(): Promise<void> {
    if (this.newName && this.newName !== this.conversation.name) {
      this.conversation.name = this.newName;
      await this.chatState.updateConversation(this.conversation);
    }
    this.editing = false;
  }

  cancelEditing(): void {
    this.editing = false;
    this.newName = '';
  }

  /**
   * Deletes the current conversation after user confirmation.
   * Prompts the user with a confirmation dialog before proceeding with the deletion.
   * If the user confirms, the conversation is deleted using the chat state service.
   *
   * @return {Promise<void>} A promise that resolves when the conversation is successfully deleted or is rejected if an error occurs.
   */
  async deleteConversation(): Promise<void> {
    if (confirm(this.translate.instant('conversationMenu.deleteConfirm'))) {
      await this.chatState.deleteConversation(this.conversation.id);
    }
  }

  /**
   * Downloads the conversation with all its messages as a JSON file, which Settings can import again.
   */
  async exportConversation(): Promise<void> {
    try {
      const file = await this.chatState.exportConversation(this.conversation.id);
      const blob = new Blob([JSON.stringify(file, null, 2) + '\n'], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = exportFileName(this.conversation.name);
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      alert(this.translate.instant('conversationMenu.exportFailed', { error: describeHttpError(error, this.translate) }));
    }
  }

  /** Every file of the conversation, to open and download: what was attached and what the agent's tools created. */
  showFiles(): void {
    this.filesDialog.open(this.conversation.id, this.conversation.name);
  }

  /** Whether the summary of this conversation is being written (summarizeConversation()). */
  get summarizing(): boolean {
    return this.chatState.isSummarizing(this.conversation.id);
  }

  /**
   * Folds the messages so far into the conversation's summary now: the model gets the summary
   * instead of them from the next answer on, which keeps a long conversation short and focused.
   */
  async summarizeConversation(): Promise<void> {
    let key: string;
    let params: Record<string, unknown> = {};
    try {
      const summary = await this.chatState.summarizeConversation(this.conversation.id);
      key = summary.messageCount === 1 ? 'conversationMenu.summarizedOne' : 'conversationMenu.summarized';
      params = { count: summary.messageCount };
    } catch (error) {
      const status = error instanceof HttpErrorResponse ? error.status : undefined;
      if (status === 429) return;  // The chat shows the guest limit
      key = status === 409 ? 'conversationMenu.nothingToSummarize'
        : status === 422 ? 'conversationMenu.tooShortToSummarize'
        : 'conversationMenu.summaryFailed';
      params = { error: describeHttpError(error, this.translate) };
    }
    this.snackBar.open(this.translate.instant(key, params), undefined, { duration: 5000 });
  }

  /** The conversation's agent has the knowledge base, so it has a memory (only for signed-in users). */
  get hasMemory(): boolean {
    return !this.auth.isGuest && !!this.catalog.getPersona(this.conversation.personaId)?.tools?.includes('knowledge_base');
  }

  /** Save what matters from this conversation to its agent's memory now, instead of after it has been quiet. */
  async reviewMemory(): Promise<void> {
    if (this.reviewingMemory) return;
    this.reviewingMemory = true;
    try {
      const result = await this.chatState.reviewMemory(this.conversation.id);
      if (result.status === 'done' && result.changes.length) {
        const vault = result.changes[0].vault;
        this.snackBar.open(this.translate.instant('conversationMenu.memorySaved', { count: result.changes.length }),
          this.translate.instant('conversationMenu.memoryShow'), { duration: 6000 })
          .onAction().subscribe(() => this.router.navigate(['/knowledge-base', 'memory'],
            { queryParams: vault ? { vault } : {} }));
        return;
      }
      const key = result.status === 'done' ? 'conversationMenu.memoryNothingToSave'
        : result.status === 'nothing_new' ? 'conversationMenu.memoryNothingNew'
        : 'conversationMenu.memoryFailed';
      this.snackBar.open(this.translate.instant(key, { error: result.detail }), undefined, { duration: 6000 });
    } catch (error) {
      this.snackBar.open(this.translate.instant('conversationMenu.memoryFailed', { error: describeHttpError(error, this.translate) }),
        undefined, { duration: 6000 });
    } finally {
      this.reviewingMemory = false;
    }
  }

  /** The server offers family mode. */
  get familyModeAvailable(): boolean {
    return this.familyMode.available;
  }

  /** The conversation's agent is hidden, which hides the conversation too; it can't be unhidden alone. */
  get agentHidden(): boolean {
    return !!this.catalog.getPersona(this.conversation.personaId)?.hidden;
  }

  get isHidden(): boolean {
    return this.familyMode.available && (!!this.conversation.hidden || this.agentHidden);
  }

  /** Who hid the chat: its agent (the persona), the agent while answering, or the user. */
  get hiddenHint(): string {
    if (this.agentHidden) return 'hide.byPersona';
    return this.conversation.hiddenBy === 'agent' ? 'hide.byAgent' : 'hide.byUser';
  }

  get hideMenuHint(): string {
    if (this.agentHidden) return 'hide.agentChatHint';
    if (this.conversation.hidden && this.conversation.hiddenBy === 'agent') return 'hide.unmarkAgentHint';
    return 'hide.markHint';
  }

  /**
   * Hide the conversation or unhide it. While this device is in family mode, a marked
   * conversation disappears at once (an open one closes), so the snackbar says so and offers Undo.
   */
  async toggleHidden(): Promise<void> {
    if (this.agentHidden) return;
    const id = this.conversation.id;
    const mark = !this.conversation.hidden;
    await this.chatState.setConversationHidden(id, mark);
    const hidden = mark && this.familyMode.active;
    const key = hidden ? 'hide.markedHidden' : mark ? 'hide.marked' : 'hide.unmarked';
    const snackBar = this.snackBar.open(this.translate.instant(key),
      hidden ? this.translate.instant('hide.undo') : undefined, { duration: 6000 });
    if (hidden) {
      snackBar.onAction().subscribe(() => void this.chatState.setConversationHidden(id, false));
    }
  }

  ngOnDestroy(): void {
    // Clean up any pending timers
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
    }
  }
}

/** The conversation's name as a file name, without the characters that file systems reject (also at the end). */
export function exportFileName(name: string): string {
  const safe = name.replace(/[<>:"/\\|?*\u0000-\u001f]+/g, ' ').replace(/\s+/g, ' ').slice(0, 80).replace(/^[\s.]+|[\s.]+$/g, '');
  return `${safe || 'conversation'}.json`;
}

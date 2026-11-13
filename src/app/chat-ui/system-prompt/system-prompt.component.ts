import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { ISystemPrompt } from '../../data/models/conversation.model';

// A prompt longer than this is shown cut, with "Show all"
const SHORT_LINES = 6;
const SHORT_CHARS = 600;

let nextId = 0;

/**
 * The system prompt the next answer gets, as the first message of the conversation (manual
 * editing): the text as the model gets it, built from the conversation's agent (its prompt, the
 * notes on its tools, its skills, MCP servers and memory) unless the conversation has its own.
 * The conversation's system messages follow it and are shown where they are.
 *
 * It can be edited (the conversation then sends exactly that text), removed (no system prompt)
 * and reset to the built one. The parent saves: `save` carries the new text, or null for a reset.
 */
@Component({
  selector: 'app-system-prompt',
  standalone: true,
  imports: [CommonModule, FormsModule, MatButtonModule, MatIconModule, MatTooltipModule, TranslateModule],
  templateUrl: './system-prompt.component.html',
  styleUrls: ['./system-prompt.component.scss']
})
export class SystemPromptComponent implements OnChanges {
  @Input({ required: true }) prompt!: ISystemPrompt;
  /** A change is being saved. */
  @Input() busy = false;
  /** The last change couldn't be saved. */
  @Input() failed = false;
  /** The new text ('' for no system prompt), or null to go back to the one built from the agent. */
  @Output() save = new EventEmitter<string | null>();

  expanded = false;
  editing = false;
  draft = '';
  readonly textId = `system-prompt-${++nextId}`;

  ngOnChanges(changes: SimpleChanges): void {
    // A saved change comes back as the new prompt: the editor has done its work
    if (changes['prompt'] && !changes['prompt'].firstChange && this.editing && !this.failed) {
      this.editing = false;
    }
  }

  /** Which of the three it is: built from the agent, the conversation's own, or none. */
  get state(): 'built' | 'custom' | 'none' {
    if (!this.prompt.custom) return 'built';
    return this.prompt.content ? 'custom' : 'none';
  }

  get long(): boolean {
    const content = this.prompt.content;
    return content.length > SHORT_CHARS || content.split('\n').length > SHORT_LINES;
  }

  get tokens(): string {
    return this.prompt.tokens.toLocaleString();
  }

  startEditing(): void {
    this.draft = this.prompt.content;
    this.editing = true;
  }

  cancel(): void {
    this.editing = false;
  }

  submit(): void {
    if (this.draft === this.prompt.content && this.prompt.custom) {
      this.editing = false;
      return;
    }
    this.save.emit(this.draft);
  }

  /** Send no system prompt at all. */
  remove(): void {
    this.save.emit('');
  }

  /** Back to the prompt built from the agent. */
  reset(): void {
    this.editing = false;
    this.save.emit(null);
  }
}

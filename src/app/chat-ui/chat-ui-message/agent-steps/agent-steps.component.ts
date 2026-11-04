import { Component, Input, Output, EventEmitter } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { IAgentStep, AgentStepType, AgentStatus } from '../../../data/models/message.model';

// Id prefix of the step that shows the oldest messages being summarized (backend/api/messages.py)
const SUMMARY_STEP_PREFIX = 'summary-';

@Component({
  selector: 'app-agent-steps',
  templateUrl: './agent-steps.component.html',
  styleUrls: ['./agent-steps.component.scss'],
  standalone: false
})
export class AgentStepsComponent {
  @Input() steps: IAgentStep[] = [];
  @Input() status: AgentStatus = 'thinking';
  @Output() expandedChange = new EventEmitter<boolean>();

  isExpanded = false;

  constructor(private translate: TranslateService) {}

  /**
   * Get the current (most recent) step
   */
  get currentStep(): IAgentStep | null {
    return this.steps.length > 0 ? this.steps[this.steps.length - 1] : null;
  }

  /**
   * Check if the agent is still processing
   */
  get isProcessing(): boolean {
    return this.status === 'thinking' || this.status === 'responding';
  }

  /**
   * The end of the reasoning text while it streams in (step_delta events), shown under the
   * collapsed panel so the thinking is visible without opening it. Once the answer is being
   * written it goes, so the answer doesn't jump up when it is done.
   */
  get liveThought(): string | null {
    const step = this.currentStep;
    if (this.status !== 'thinking' || this.isExpanded || !step || step.type !== 'thought' || !step.content) {
      return null;
    }
    const text = step.content.trim();
    if (text.length <= 280) return text;
    const tail = text.slice(-280);
    const wordStart = tail.indexOf(' ');
    return '…' + (wordStart >= 0 && wordStart < 40 ? tail.slice(wordStart + 1) : tail);
  }

  /**
   * Get dynamic header text based on status and current step
   */
  get headerText(): string {
    if (this.isProcessing && this.currentStep) {
      // Show current action while processing
      return this.currentStep.title;
    } else if (this.status === 'error') {
      return this.translate.instant('message.steps.error');
    } else {
      // Show summary when complete
      return this.translate.instant('message.steps.title');
    }
  }

  /**
   * Spelled-out step count for the tooltip and screen readers (the badge shows only the number)
   */
  get stepCountLabel(): string {
    return this.steps.length === 1
      ? this.translate.instant('message.steps.countOne')
      : this.translate.instant('message.steps.count', { count: this.steps.length });
  }

  /**
   * How long a step took, readable at a glance: "530 ms", "2.2 s", "14 s", "1 min 5 s"
   */
  formatDuration(ms: number): string {
    if (ms < 1000) {
      return `${Math.round(ms)} ms`;
    }
    const seconds = ms / 1000;
    if (seconds < 10) {
      const locale = this.translate.currentLang || 'en';
      const text = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(seconds);
      return `${text} s`;
    }
    if (seconds < 60) {
      return `${Math.round(seconds)} s`;
    }
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round(seconds % 60);
    return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
  }

  /**
   * Get icon for an agent step: by its type, or the summary of the oldest messages
   */
  getStepIcon(step: IAgentStep): string {
    if (step.id.startsWith(SUMMARY_STEP_PREFIX)) {
      return 'summarize';
    }
    const type: AgentStepType = step.type;
    const icons: Record<AgentStepType, string> = {
      thought: 'psychology',
      tool_call: 'build',
      tool_result: 'check_circle',
      observation: 'visibility',
    };
    return icons[type] || 'circle';
  }

  /**
   * The note a knowledge base tool's result is about (kb_read, kb_write, kb_update, kb_archive,
   * and "memory" for the memory tools), to open it on the Knowledge base page
   */
  noteSlug(step: IAgentStep): string | null {
    const slug = step.type === 'tool_result' ? step.metadata?.['kbNote'] : null;
    return typeof slug === 'string' && slug ? slug : null;
  }

  /** The knowledge base of that note: an agent's own one ({vault: id}), else the shared one (no parameter) */
  noteVault(step: IAgentStep): Record<string, number> | null {
    const vault = step.metadata?.['kbVault'];
    return typeof vault === 'number' && vault > 0 ? { vault } : null;
  }

  /**
   * TrackBy function for agent steps
   */
  trackStep(index: number, step: IAgentStep): string {
    return step.id;
  }

  /**
   * Handle expansion state change
   */
  onExpandedChange(expanded: boolean): void {
    this.isExpanded = expanded;
    this.expandedChange.emit(expanded);
  }
}

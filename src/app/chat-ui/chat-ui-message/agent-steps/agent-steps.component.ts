import { Component, Input, Output, EventEmitter } from '@angular/core';
import { IAgentStep, AgentStepType, AgentStatus } from '../../../data/models/message.model';

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
   * collapsed panel so the thinking is visible without opening it.
   */
  get liveThought(): string | null {
    const step = this.currentStep;
    if (!this.isProcessing || this.isExpanded || !step || step.type !== 'thought' || !step.content) {
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
      return 'Error occurred';
    } else {
      // Show summary when complete
      return 'Thought process';
    }
  }

  /**
   * Spelled-out step count for the tooltip and screen readers (the badge shows only the number)
   */
  get stepCountLabel(): string {
    return `${this.steps.length} ${this.steps.length === 1 ? 'step' : 'steps'}`;
  }

  /**
   * Get icon for agent step type
   */
  getStepIcon(type: AgentStepType): string {
    const icons: Record<AgentStepType, string> = {
      thought: 'psychology',
      tool_call: 'build',
      tool_result: 'check_circle',
      observation: 'visibility',
    };
    return icons[type] || 'circle';
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

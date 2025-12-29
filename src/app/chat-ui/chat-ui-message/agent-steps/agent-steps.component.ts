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

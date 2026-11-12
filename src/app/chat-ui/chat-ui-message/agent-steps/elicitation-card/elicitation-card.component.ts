import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IAgentStep } from '../../../../data/models/message.model';
import {
  IMcpElicitation, IMcpElicitationProperty, McpElicitationAction
} from '../../../../data/models/mcp.model';
import { ApiService } from '../../../../services/api.service';

/** The question of an MCP server in a step's metadata (an elicitation step), or null. */
export function elicitationOf(step: IAgentStep): IMcpElicitation | null {
  const question = step.metadata?.['elicitation'];
  return question && typeof question === 'object' ? question as IMcpElicitation : null;
}

interface Choice {
  value: string;
  label: string;
}

/** One field of a form question, ready for the template. */
interface Field {
  name: string;
  label: string;
  description?: string;
  required: boolean;
  kind: 'text' | 'number' | 'boolean' | 'select' | 'multi';
  inputType: string;  // For text and number fields
  choices: Choice[];
  min?: number;
  max?: number;
  step?: number;
  minLength?: number;
  maxLength?: number;
}

const INPUT_TYPES: Record<string, string> = { email: 'email', uri: 'url', date: 'date', 'date-time': 'datetime-local' };

function choicesOf(property: { enum?: string[]; enumNames?: string[]; oneOf?: Array<{ const: string; title?: string }>;
                               anyOf?: Array<{ const: string; title?: string }> } | undefined): Choice[] {
  if (!property) return [];
  if (Array.isArray(property.enum)) {
    return property.enum.map((value, index) => ({ value, label: property.enumNames?.[index] ?? value }));
  }
  const options = property.oneOf ?? property.anyOf;
  return Array.isArray(options)
    ? options.filter(option => option && 'const' in option).map(option => ({ value: option.const, label: option.title ?? option.const }))
    : [];
}

function fieldOf(name: string, property: IMcpElicitationProperty, required: boolean): Field {
  const field: Field = {
    name, required, label: property.title || name, description: property.description,
    kind: 'text', inputType: 'text', choices: []
  };
  if (property.type === 'boolean') {
    field.kind = 'boolean';
  } else if (property.type === 'array') {
    field.kind = 'multi';
    field.choices = choicesOf(property.items);
  } else if (property.type === 'number' || property.type === 'integer') {
    field.kind = 'number';
    field.inputType = 'number';
    field.min = property.minimum;
    field.max = property.maximum;
    field.step = property.type === 'integer' ? 1 : undefined;
  } else {
    field.choices = choicesOf(property);
    if (field.choices.length) {
      field.kind = 'select';
    } else {
      field.inputType = INPUT_TYPES[property.format ?? ''] ?? 'text';
      field.minLength = property.minLength;
      field.maxLength = property.maxLength;
    }
  }
  return field;
}

/**
 * A question of an MCP server while one of its tools runs (elicitation, docs/mcp.md): the
 * server's message, the form's fields (form mode) or the page it wants opened (URL mode), and
 * the buttons to answer. The answer goes to the backend, which passes it to the waiting tool
 * call; the stream then replaces the step, and the card goes.
 */
@Component({
  selector: 'app-elicitation-card',
  standalone: true,
  imports: [CommonModule, FormsModule, MatButtonModule, MatCheckboxModule, MatFormFieldModule, MatIconModule,
            MatInputModule, MatSelectModule, TranslateModule],
  templateUrl: './elicitation-card.component.html',
  styleUrls: ['./elicitation-card.component.scss']
})
export class ElicitationCardComponent implements OnChanges {
  @Input({ required: true }) step!: IAgentStep;

  question: IMcpElicitation | null = null;
  fields: Field[] = [];
  values: Record<string, unknown> = {};
  sending = false;
  error: string | null = null;
  // Plain confirmations: accept the server's ones without asking from now on
  rememberChat = false;
  rememberAlways = false;

  constructor(private api: ApiService, private translate: TranslateService) {}

  ngOnChanges(): void {
    const question = elicitationOf(this.step);
    if (question?.id !== this.question?.id) {
      this.fields = [];
      this.values = {};
      const properties = question?.schema?.properties ?? {};
      const required = new Set(question?.schema?.required ?? []);
      for (const [name, property] of Object.entries(properties)) {
        const field = fieldOf(name, property ?? {}, required.has(name));
        this.fields.push(field);
        const fallback = field.kind === 'boolean' ? false : field.kind === 'multi' ? [] : null;
        this.values[name] = property?.default ?? fallback;
      }
      this.sending = false;
      this.error = null;
      this.rememberChat = false;
      this.rememberAlways = false;
    }
    this.question = question;
  }

  get urlMode(): boolean {
    return this.question?.mode === 'url';
  }

  /** The host of the page in URL mode, shown so the user sees where it goes. */
  get host(): string {
    try {
      return new URL(this.question?.url ?? '').host;
    } catch {
      return this.question?.url ?? '';
    }
  }

  /** Every required field has a value (booleans always have one). */
  get complete(): boolean {
    return this.fields.every(field => {
      if (!field.required || field.kind === 'boolean') return true;
      const value = this.values[field.name];
      return Array.isArray(value) ? value.length > 0 : value !== null && value !== undefined && value !== '';
    });
  }

  async answer(action: McpElicitationAction): Promise<void> {
    const question = this.question;
    if (!question || this.sending) return;
    if (action === 'accept' && this.urlMode && question.url) {
      // Open it within the click, so the browser doesn't block the new tab
      window.open(question.url, '_blank', 'noopener,noreferrer');
    }
    this.sending = true;
    this.error = null;
    try {
      const remember = action !== 'accept' || !question.confirmation ? null
        : this.rememberAlways ? 'always' : this.rememberChat && question.conversation ? 'conversation' : null;
      await this.api.answerMcpElicitation(question.id, action,
        action === 'accept' && !this.urlMode ? this.content() : undefined, remember);
      // The stream replaces the step with the outcome; the card goes then
    } catch (error) {
      this.sending = false;
      const response = error instanceof HttpErrorResponse ? error : null;
      this.error = response?.status === 404
        ? this.translate.instant('message.question.closed')
        : (typeof response?.error?.detail === 'string' ? response.error.detail
          : this.translate.instant('message.question.failed'));
    }
  }

  /** The form's values without the empty ones. */
  private content(): Record<string, unknown> {
    const content: Record<string, unknown> = {};
    for (const field of this.fields) {
      const value = this.values[field.name];
      if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue;
      content[field.name] = value;
    }
    return content;
  }
}

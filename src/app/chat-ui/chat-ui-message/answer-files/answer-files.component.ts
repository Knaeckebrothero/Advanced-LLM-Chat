import { Component, DoCheck, HostBinding, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslateModule } from '@ngx-translate/core';
import { IFileRef } from '../../../data/models/file.model';
import { IAgentStep } from '../../../data/models/message.model';
import { FileTileComponent } from '../../../components/file-tile/file-tile.component';

/** The files in a step's metadata under a key (`files`: a tool created them; `shownFiles`: the agent shows them). */
export function stepFiles(step: IAgentStep, key: 'files' | 'shownFiles'): IFileRef[] {
  const files = step.type === 'tool_result' ? step.metadata?.[key] : null;
  if (!Array.isArray(files)) return [];
  return files.filter((file): file is IFileRef =>
    !!file && typeof file.fileId === 'string' && typeof file.name === 'string' && typeof file.mimeType === 'string');
}

/**
 * The files of an answer's steps that its text doesn't place: the ones that are shown anyway
 * (`shownFiles`), and the other ones its tools created, each once and in the steps' order.
 */
export function unplacedFiles(steps: IAgentStep[], placed: ReadonlySet<string>): { shown: IFileRef[]; created: IFileRef[] } {
  const shown = new Map<string, IFileRef>();
  const created = new Map<string, IFileRef>();
  for (const step of steps) {
    for (const file of stepFiles(step, 'shownFiles')) shown.set(file.fileId, file);
    for (const file of stepFiles(step, 'files')) created.set(file.fileId, file);
  }
  return {
    shown: [...shown.values()].filter(file => !placed.has(file.fileId)),
    created: [...created.values()].filter(file => !shown.has(file.fileId) && !placed.has(file.fileId))
  };
}

/**
 * The files of an answer that it doesn't place in its text (docs/files.md), between its steps
 * and its text: the ones that are shown anyway (the files of an agent that isn't told how to
 * place them, and what show_file showed in older answers), large, and under them the other
 * files its tools created, as small previews, so nothing a tool made stays hidden in a
 * collapsed step. Both come from the steps' metadata, so they appear while the answer runs and
 * stay with the stored message.
 */
@Component({
  selector: 'app-answer-files',
  standalone: true,
  imports: [CommonModule, TranslateModule, FileTileComponent],
  templateUrl: './answer-files.component.html',
  styleUrls: ['./answer-files.component.scss']
})
export class AnswerFilesComponent implements DoCheck {
  @Input() steps: IAgentStep[] = [];
  /** The files the answer places in its text (their IDs): those are not shown here again. */
  @Input() placed: ReadonlySet<string> = new Set<string>();
  /** The message's images, which the preview steps through from the one that is opened. */
  @Input() gallery?: IFileRef[];

  shown: IFileRef[] = [];
  created: IFileRef[] = [];  // Created in the answer, not shown
  private seen = '';

  @HostBinding('class.is-empty')
  get empty(): boolean {
    return !this.shown.length && !this.created.length;
  }

  ngDoCheck(): void {
    // The steps grow in place while the answer streams; a tool result is never replaced
    const state = `${this.steps.length}:${this.steps[this.steps.length - 1]?.id ?? ''}:${[...this.placed].join()}`;
    if (state === this.seen) return;
    this.seen = state;
    ({ shown: this.shown, created: this.created } = unplacedFiles(this.steps, this.placed));
  }

  trackFile(index: number, file: IFileRef): string {
    return file.fileId;
  }
}

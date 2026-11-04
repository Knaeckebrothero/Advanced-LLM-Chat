import { TranslateService } from '@ngx-translate/core';
import { IKBRevisionSummary, RevisionAction } from '../data/models/knowledge-base.model';

/** Date and time in the language of the app, e.g. "4 Nov 2026, 09:32". */
export function formatDateTime(value: string | null | undefined, translate: TranslateService): string {
  if (!value) return '';
  const date = new Date(value);
  if (isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(translate.currentLang || 'en', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

/** Only the date, e.g. "4 Nov 2026". */
export function formatDate(value: string | null | undefined, translate: TranslateService): string {
  if (!value) return '';
  const date = new Date(value);
  if (isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(translate.currentLang || 'en', { dateStyle: 'medium' }).format(date);
}

/** Who wrote a version: "you", the agent's name, or "an agent". */
export function authorLabel(revision: IKBRevisionSummary, translate: TranslateService): string {
  if (revision.author === 'user') return translate.instant('knowledgeBase.note.you');
  return revision.personaName || translate.instant('knowledgeBase.note.agent');
}

export const REVISION_ICONS: Record<RevisionAction, string> = {
  create: 'add_circle_outline',
  update: 'edit_note',
  archive: 'inventory_2',
  restore: 'unarchive'
};

/** "Created", "Changed", "Archived", "Restored". */
export function actionLabel(action: string, translate: TranslateService): string {
  const known = action in REVISION_ICONS ? action : 'update';
  return translate.instant(`knowledgeBase.history.${known}`);
}

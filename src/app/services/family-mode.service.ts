import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, combineLatest } from 'rxjs';
import { distinctUntilChanged, map, shareReplay } from 'rxjs/operators';

/** What hides a conversation: its own mark and its agent. */
export interface HideableConversation {
  hidden?: boolean;
  personaId?: number | null;
}

/** An agent as far as family mode cares: its id and whether it is hidden. */
export interface HideablePersona {
  id: number;
  hidden?: boolean;
}

/**
 * Family mode of this device (localStorage, on for a new device): conversations, agents, notes and
 * lines tagged #hidden that are hidden don't show, and every request carries the header
 * X-Family-Mode, so the server leaves them out too, also for the agent that answers. A switch in the
 * settings turns it off and on, or, with FAMILY_MODE_SWITCH=logo, five quick taps on the sidebar's logo
 * (SidebarComponent.onLogoTap()).
 *
 * The server can switch the feature off (FAMILY_MODE_ENABLED, familyModeAvailable in
 * GET /api/auth/config): then nothing is hidden.
 */
@Injectable({ providedIn: 'root' })
export class FamilyModeService {
  static readonly STORAGE_KEY = 'familyMode';
  static readonly HEADER = 'X-Family-Mode';

  private readonly availableSubject = new BehaviorSubject<boolean>(true);
  /** How it is turned off and on: a switch in the settings, or five taps on the logo (FAMILY_MODE_SWITCH). */
  switchKind: 'settings' | 'logo' = 'settings';
  private readonly onSubject = new BehaviorSubject<boolean>(FamilyModeService.readOn());

  /** The server offers family mode. */
  readonly available$: Observable<boolean> = this.availableSubject.pipe(distinctUntilChanged());
  /** Family mode is on: hidden content is hidden on this device. */
  readonly active$: Observable<boolean> = combineLatest([this.available$, this.onSubject]).pipe(
    map(([available, on]) => available && on),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: false })
  );

  get available(): boolean {
    return this.availableSubject.value;
  }

  /** Family mode is on (for requests). */
  get active(): boolean {
    return this.availableSubject.value && this.onSubject.value;
  }

  /** From the server's config (AuthService); a server that doesn't say offers it, with the settings switch. */
  setAvailable(available: boolean | undefined, switchKind?: 'settings' | 'logo'): void {
    this.switchKind = switchKind === 'logo' ? 'logo' : 'settings';
    this.availableSubject.next(available !== false);
  }

  /** Turn family mode off or on again on this device. */
  toggle(): void {
    this.setOn(!this.onSubject.value);
  }

  setOn(on: boolean): void {
    try {
      localStorage.setItem(FamilyModeService.STORAGE_KEY, on ? 'on' : 'off');
    } catch {
      // Without storage it lasts until the page is reloaded
    }
    this.onSubject.next(on);
  }

  /** The headers that tell the server the device is in family mode, or none while it is off. */
  headers(): Record<string, string> {
    return this.active ? { [FamilyModeService.HEADER]: '1' } : {};
  }

  /** The conversation is hidden, or its agent is. */
  static isConversationHidden(conversation: HideableConversation | null | undefined,
                              hiddenPersonas: ReadonlySet<number>): boolean {
    if (!conversation) return false;
    return !!conversation.hidden || (conversation.personaId != null && hiddenPersonas.has(conversation.personaId));
  }

  /** The ids of the hidden agents of a list. */
  static hiddenPersonaIds(personas: readonly HideablePersona[]): Set<number> {
    return new Set(personas.filter(persona => persona.hidden).map(persona => persona.id));
  }

  private static readOn(): boolean {
    try {
      return localStorage.getItem(FamilyModeService.STORAGE_KEY) !== 'off';
    } catch {
      return true;
    }
  }
}

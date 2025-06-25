import { Injectable } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';

export type MessageType = 'success' | 'error' | 'info' | 'warning';

export interface StatusMessage {
  text: string;
  type: MessageType;
}

@Injectable({
  providedIn: 'root'
})
export class StatusBarService {

  private showSidenavSource = new BehaviorSubject<boolean>(false);
  showSidenav$ = this.showSidenavSource.asObservable();

  private messageSource = new Subject<StatusMessage>();
  message$ = this.messageSource.asObservable();

  constructor() { }

  toggleSidenav() {
    this.showSidenavSource.next(!this.showSidenavSource.value);
  }

  showMessage(text: string, type: MessageType) {
    this.messageSource.next({ text, type });
  }
}

import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class StatusBarService {

  constructor() { }
  
  private showSidenavSource = new BehaviorSubject<boolean>(false);
  showSidenav$ = this.showSidenavSource.asObservable();

  toggleSidenav() {
    this.showSidenavSource.next(!this.showSidenavSource.value);
  }
}

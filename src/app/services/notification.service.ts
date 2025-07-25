import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface Notification {
  message: string;
  type: 'info' | 'warning' | 'error' | 'success';
  duration?: number;
  id?: string;
}

@Injectable({
  providedIn: 'root'
})
export class NotificationService {
  private notifications$ = new BehaviorSubject<Notification[]>([]);
  
  get notifications(): Observable<Notification[]> {
    return this.notifications$.asObservable();
  }
  
  show(message: string, type: Notification['type'] = 'info', duration: number = 5000): void {
    const notification: Notification = {
      message,
      type,
      duration,
      id: `${Date.now()}-${Math.random()}`
    };
    
    const current = this.notifications$.getValue();
    this.notifications$.next([...current, notification]);
    
    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        this.remove(notification.id!);
      }, duration);
    }
  }
  
  showError(message: string, duration: number = 5000): void {
    this.show(message, 'error', duration);
  }
  
  showSuccess(message: string, duration: number = 3000): void {
    this.show(message, 'success', duration);
  }
  
  showWarning(message: string, duration: number = 5000): void {
    this.show(message, 'warning', duration);
  }
  
  showInfo(message: string, duration: number = 3000): void {
    this.show(message, 'info', duration);
  }
  
  remove(id: string): void {
    const current = this.notifications$.getValue();
    this.notifications$.next(current.filter(n => n.id !== id));
  }
  
  clear(): void {
    this.notifications$.next([]);
  }
}
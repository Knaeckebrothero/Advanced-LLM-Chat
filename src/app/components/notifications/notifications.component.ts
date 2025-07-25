import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NotificationService, Notification } from '../../services/notification.service';
import { Observable } from 'rxjs';
import { animate, style, transition, trigger } from '@angular/animations';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="notifications-container">
      <div *ngFor="let notification of notifications$ | async"
           class="notification"
           [class.notification-error]="notification.type === 'error'"
           [class.notification-warning]="notification.type === 'warning'"
           [class.notification-success]="notification.type === 'success'"
           [class.notification-info]="notification.type === 'info'"
           @slideIn>
        <div class="notification-content">
          <span class="notification-icon">
            <span *ngIf="notification.type === 'error'">⚠️</span>
            <span *ngIf="notification.type === 'warning'">⚡</span>
            <span *ngIf="notification.type === 'success'">✅</span>
            <span *ngIf="notification.type === 'info'">ℹ️</span>
          </span>
          <span class="notification-message">{{ notification.message }}</span>
          <button class="notification-close" (click)="close(notification.id!)">×</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .notifications-container {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 1000;
      max-width: 400px;
    }
    
    .notification {
      background: white;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      margin-bottom: 10px;
      overflow: hidden;
      border-left: 4px solid;
    }
    
    .notification-error {
      border-left-color: #f44336;
    }
    
    .notification-warning {
      border-left-color: #ff9800;
    }
    
    .notification-success {
      border-left-color: #4caf50;
    }
    
    .notification-info {
      border-left-color: #2196f3;
    }
    
    .notification-content {
      display: flex;
      align-items: center;
      padding: 16px;
      gap: 12px;
    }
    
    .notification-icon {
      font-size: 20px;
    }
    
    .notification-message {
      flex: 1;
      color: #333;
    }
    
    .notification-close {
      background: none;
      border: none;
      font-size: 24px;
      color: #999;
      cursor: pointer;
      padding: 0;
      width: 24px;
      height: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .notification-close:hover {
      color: #666;
    }
    
    @media (max-width: 600px) {
      .notifications-container {
        left: 10px;
        right: 10px;
        max-width: none;
      }
    }
  `],
  animations: [
    trigger('slideIn', [
      transition(':enter', [
        style({ transform: 'translateX(100%)', opacity: 0 }),
        animate('300ms ease-out', style({ transform: 'translateX(0)', opacity: 1 }))
      ]),
      transition(':leave', [
        animate('300ms ease-in', style({ transform: 'translateX(100%)', opacity: 0 }))
      ])
    ])
  ]
})
export class NotificationsComponent implements OnInit {
  notifications$: Observable<Notification[]>;
  
  constructor(private notificationService: NotificationService) {
    this.notifications$ = this.notificationService.notifications;
  }
  
  ngOnInit(): void {}
  
  close(id: string): void {
    this.notificationService.remove(id);
  }
}
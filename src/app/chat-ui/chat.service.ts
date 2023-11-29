import { Injectable, OnInit } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from './message.model';

@Injectable({
  providedIn: 'root'
})
export class ChatService implements OnInit {

  // The BehaviorSubject is a special type of observable that allows us to set the initial value of the observable.
  private messagesSubject = new BehaviorSubject<Message[]>([]);
  // The messages$ observable is exposed as a public property of the ChatService.
  public messages$: Observable<Message[]> = this.messagesSubject.asObservable();

  // The ChatService is responsible for managing the messages array and exposing it as an observable.
  ngOnInit() {

  }

  /*
  The ChatService exposes a veriety of methods for managing the message history.
  */

  // Add a new message to the messages array.
  public addMessage(content: any, isUser:boolean) {

  }

  // Update an existing message in the messages array.
  public updateMessage(message: Message) {

  }

  // Delete a message from the messages array.
  public deleteMessage(timestamp: number) {

  }

  // Delete all messages from the messages array.
  public deleteAllMessages() {

  }
}

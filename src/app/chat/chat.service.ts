import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/chat-message';
import { DataService } from '../data/data.service';


@Injectable({
  providedIn: 'root'
})
export class ChatService {

  // The ChatService is responsible for managing the messages array and exposing it as an observable.
  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Inject the DataService and load the messages from the database
  constructor(private dataService: DataService) {
    // Wait for the database to be ready
    this.dataService.getDatabaseReadyPromise().then(() => {
      // Load the messages from the database once it has been started
      console.log("Loading messages from the database...");
      this.dataService.getAllMessages().then((messages: Message[]) => {
        // Add the messages to the messages array
        this.messagesSubject.next(messages);
      });
      console.log("Messages loaded!");
    });
  }

  /*
  The ChatService exposes a veriety of methods for managing the message history.
  */

  // Add a new message to the messages array
  public addMessage(content: any, isUser:boolean) {
    // Get the current date and time
    const msgDate = new Date();

    // Create a new message object
    const newMessage = {
      id: "test-" + msgDate,
      content: content,
      time: msgDate,
      isUser: isUser
    };

    // Add the message to the database
    this.dataService.addMessage(newMessage);

    // Add the message to the messages array
    this.messagesSubject.next([...this.messagesSubject.getValue(), newMessage]);
  }

  // Update an existing message in the messages array
  public updateMessage(message: Message) {

  }

  // Delete a message from the messages array
  public deleteMessage(timestamp: number) {

  }

  // Delete all messages from the messages array
  public deleteAllMessages() {

  }
}

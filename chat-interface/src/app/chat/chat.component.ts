import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';

interface ChatResponse {
  text: string,
  isUser: boolean,
  time: Date
}

@Component({
  selector: 'app-chat',
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.scss']
})

export class ChatComponent {
  constructor(private http: HttpClient) { }
  newMessage: string = '';
  //messages: ChatResponse [] = [];
  messages: ChatResponse [] = [];

  sendMessage() {
    const currentTime = new Date();
    const payload = { text: this.newMessage, isUser: true, time: currentTime };

    this.http.post<ChatResponse>('http://127.0.0.1:8000/api/chat', payload).subscribe({
      next: (response) => {
        this.messages.push({ text: response.text, isUser: false, time: new Date(response.time) });
      },
      error: (error) => {
        console.error('There was an error!', error);
      }
    });
    
    this.messages.push(payload);
    this.newMessage = '';
  }
}

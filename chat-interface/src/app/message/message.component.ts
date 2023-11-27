import { Component, Input } from '@angular/core';

interface Message {
  text: string;
  isUser: boolean;
  time: Date;
}

@Component({
  selector: 'app-message',
  templateUrl: './message.component.html',
  styleUrls: ['./message.component.scss']
})
export class MessageComponent {
  @Input() message!: Message;
  constructor() { }
}

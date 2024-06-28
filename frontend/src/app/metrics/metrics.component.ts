import { Component, OnInit } from '@angular/core';
import { ChatService } from '../chat/chat.service';

@Component({
  selector: 'app-metrics',
  templateUrl: './metrics.component.html',
  styleUrls: ['./metrics.component.scss']
})
export class MetricsComponent implements OnInit {

  summary: string = "";

  constructor(private serviceChat: ChatService) { }

  ngOnInit(): void {
    this.refreshSummary()
  }

  refreshSummary() {
    this.summary = this.serviceChat.getSummary();
  }

  updateSummary() {
    this.serviceChat.setSummary(this.summary);
  }

  onFileSelected(event: any) {
    const file: File = event.target.files[0];

    if (file) {
      const fileReader = new FileReader();
      fileReader.onload = (e) => {
        // This will print the file content to the console
        console.log(JSON.parse(fileReader.result as string));
      };
      fileReader.readAsText(file);
    }
  }
}

import { Component, OnInit } from '@angular/core';
import { ChatService } from '../services/chat.service';

@Component({
    selector: 'app-metrics',
    templateUrl: './metrics.component.html',
    styleUrls: ['./metrics.component.scss'],
    standalone: false
})
export class MetricsComponent implements OnInit {

  summary: string = "";

  constructor(private serviceChat: ChatService) { }

  ngOnInit(): void {
    this.refreshSummary()
  }

  refreshSummary() {
    console.log("Refreshing summary");
  }

  updateSummary() {
    console.log("Updating summary");
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

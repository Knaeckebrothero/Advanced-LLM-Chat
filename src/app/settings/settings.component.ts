import { Component } from '@angular/core';
import { DBService } from '../data/db.service';


@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent {

  constructor(private dbService: DBService) { }

  onFileSelected(event: any) {
    const file: File = event.target.files[0];

    if (file) {
      const fileReader = new FileReader();
      fileReader.onload = async (e) => {
        // Parse the uploaded file content
        const jsonConfig = JSON.parse(fileReader.result as string);

        if (jsonConfig.settings) {
          await this.dbService.addLLMConfig(jsonConfig.settings);
          console.log('Settings added!');
        }

        if (jsonConfig.agents) {
          for (const agent of jsonConfig.agents) {
            await this.dbService.addAgent(agent);
          }
          console.log('Agents added!');
        }

        if (jsonConfig.conversation) {
          await this.dbService.addConversation(jsonConfig.conversation);
          console.log('Conversation added!');
        }
      };
      fileReader.readAsText(file);
    }
  }

  // Delete messages from the database
  resetMessages(){
    // Get all the messages from the database
    this.dbService.getAllMessages().then((messages) => {
      this.dbService.getConversation(1).then((conversation) => {
      // Convert messages to JSON format
      if(conversation === undefined){
        conversation = {id: 1,
            messagesPartOfSummary: 0,
            enviorementVariables: [],
            summary: '',
            participants: []
          }
      }

      // Convert messages to JSON format
      const messagesJson = JSON.stringify(messages);

      // Create a blob with the JSON content
      const blob = new Blob([JSON.stringify(conversation), messagesJson], { type: 'application/json' });

      // Create a link element to download the blob
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'Conversation_' + new Date().getUTCDate().toString() +'.'+ new Date().getMonth().toString() +'.'+ new Date().getFullYear().toString() + '_messages.json'; // Name of the file to be downloaded
      document.body.appendChild(a); // Append the link to the document
      a.click(); // Simulate click on the link to trigger the download
      document.body.removeChild(a); // Remove the link from the document

      // Delete all the messages after backup
      this.dbService.deleteAllMessages().then(() => {
        this.dbService.deleteConversation(1).then(() => {
          console.log('Conversation deleted!');
        });
        console.log('All messages deleted!');
      });
    });
  });
  }
}

import { Component } from '@angular/core';
import { FormControl, FormGroup } from '@angular/forms';
import { OnInit } from '@angular/core';
import { DBService } from '../data/db.service';


@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent implements OnInit{
  // Settings form
  settingsForm = new FormGroup({
    id: new FormControl('openai-default'),
    name: new FormControl(),
    apiKey: new FormControl(),
    model: new FormControl(),
    frequency_penalty: new FormControl(),
    top_logprobs: new FormControl(),
    max_tokens: new FormControl(),
    n: new FormControl(),
    presence_penalty: new FormControl(),
    seed: new FormControl(),
    temperature: new FormControl(),
    top_p: new FormControl(),
    user: new FormControl(),
  });

  agentForm = new FormGroup({
    role: new FormControl(),
    prompt: new FormControl()
  });

  constructor(private dbService: DBService) { }

  // Initialize the input fields on component start
  ngOnInit() {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(async () => {
      // Get the settings from the database
      const settings = await this.dbService.getLLMConfig(this.settingsForm.value.id!);
  
      // Check if the settings are found
      if (settings === undefined) {
        console.error("Settings " + this.settingsForm.value.id + " not found!");
      } else {
        // Values need to be converted to string for the form to accept them
        this.settingsForm.patchValue(settings);
      }
    });
  }

  // Save settings to the database
  saveSettings() {
    this.dbService.addLLMConfig(this.settingsForm.value);
    console.log('Settings ' + this.settingsForm.value.id + ' saved!');
  }

  addAgent() {
    this.dbService.addAgent({id: "default-agent-01", role: this.agentForm.value.role, prompt: this.agentForm.value.prompt});
    console.log('Agent added!');
  }

  // Delete messages from the database
  resetMessages(){
    // Get all the messages from the database
    this.dbService.getAllMessages().then((messages) => {
      const conversation = this.dbService.getConversation("default-conv-01").then((conversation) => {return conversation;});
      const conversationJson = JSON.stringify(conversation);

      // Convert messages to JSON format
      const messagesJson = JSON.stringify(messages);

      // Create a blob with the JSON content
      const blob = new Blob([conversationJson, messagesJson], { type: 'application/json' });

      // Create a link element to download the blob
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'messages_backup.json'; // Name of the file to be downloaded
      document.body.appendChild(a); // Append the link to the document
      a.click(); // Simulate click on the link to trigger the download
      document.body.removeChild(a); // Remove the link from the document

      // Delete all the messages after backup
      this.dbService.deleteAllMessages().then(() => {
        this.dbService.deleteConversation("default-conv-01").then(() => {
          console.log('Conversation deleted!');
        });
        console.log('All messages deleted!');
      });
    });
  }
}

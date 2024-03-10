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
    id: new FormControl({value: 'openai-default', disabled: true}),
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
    user: new FormControl()
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
}

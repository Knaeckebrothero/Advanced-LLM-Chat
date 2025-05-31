import { Component } from '@angular/core';
import {DisplayService} from "./sidebar/service/display.service";

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false // This makes AppComponent a non-standalone component
})
export class AppComponent {
  title = 'Advanced LLM Chat';

  // Make displayService public to allow template to access its methods and observables
  constructor(public displayService: DisplayService) { }
}

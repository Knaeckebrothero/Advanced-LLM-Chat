import { Component } from '@angular/core';
import { DBService } from '../data/db.service';


@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent {

  constructor(private dbService: DBService) {}

}

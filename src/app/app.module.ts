// Components
import { ChatUiComponent } from './chat-ui/chat-ui.component';
import { ChatUiMessageComponent } from './chat-ui/chat-ui-message/chat-ui-message.component';
import { SettingsComponent } from './settings/settings.component';

// Angular Material
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTabsModule } from '@angular/material/tabs';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';

// Default
import { NgModule, isDevMode } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppComponent } from './app.component';
import { ServiceWorkerModule } from '@angular/service-worker';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { HttpClientModule } from '@angular/common/http';
import { ReactiveFormsModule } from '@angular/forms';
import { FormsModule } from '@angular/forms';
import { MetricsComponent } from './metrics/metrics.component';


@NgModule({
  declarations: [
    AppComponent,
    ChatUiComponent,
    ChatUiMessageComponent,
    SettingsComponent,
    MetricsComponent,
  ],
  imports: [
    BrowserModule,
    MatIconModule,
    MatInputModule,
    FormsModule,
    MatTabsModule,
    HttpClientModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    ServiceWorkerModule.register('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000'
    }),
    BrowserAnimationsModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }

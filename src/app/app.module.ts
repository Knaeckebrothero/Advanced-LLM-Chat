// Components
import { ChatUiComponent } from './chat-ui/chat-ui.component';
import { ChatUiMessageComponent } from './chat-ui/chat-ui-message/chat-ui-message.component';
import { SettingsComponent } from './settings/settings.component';
import { MetricsComponent } from './metrics/metrics.component';
import { StatusBarComponent } from './status-bar/status-bar.component';
import { AuthCallbackComponent } from './auth/auth-callback/auth-callback.component';
import { AuthGuard } from './auth/auth.guard';
import { LoginComponent } from './login/login.component';

// Services
import { AuthService } from './auth/auth.service';

// Angular Material
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

// Default
import {NgModule, isDevMode, provideAppInitializer, inject} from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppComponent } from './app.component';
import { ServiceWorkerModule } from '@angular/service-worker';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';
import { ReactiveFormsModule } from '@angular/forms';
import { FormsModule } from '@angular/forms';
import { RouterModule, Routes } from '@angular/router';


// Routes
const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: '', component: ChatUiComponent, canActivate: [AuthGuard] },
  { path: 'metrics', component: MetricsComponent, canActivate: [AuthGuard] },
  { path: 'settings', component: SettingsComponent, canActivate: [AuthGuard] },
  { path: 'auth/callback', component: AuthCallbackComponent },
];

@NgModule({ declarations: [
  AppComponent,
  ChatUiComponent,
  ChatUiMessageComponent,
  SettingsComponent,
  MetricsComponent,
  StatusBarComponent,
  AuthCallbackComponent,
  LoginComponent,
  ],
  bootstrap: [AppComponent],
  imports: [
    BrowserModule,
    MatIconModule,
    MatInputModule,
    FormsModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSidenavModule,
    MatListModule,
    MatProgressSpinnerModule,
    RouterModule.forRoot(routes),
    ServiceWorkerModule.register(
      'ngsw-worker.js', {
        enabled: !isDevMode(),
        registrationStrategy: 'registerWhenStable:30000'
      }),
    BrowserAnimationsModule
  ],
  providers: [
    provideHttpClient(withInterceptorsFromDi()),
    provideAppInitializer(() => {
      const authService = inject(AuthService);
      return authService.initializeAuth();
    })
  ]
})
export class AppModule { }

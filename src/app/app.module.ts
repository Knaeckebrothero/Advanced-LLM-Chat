// Components
import { ChatUiComponent } from './chat-ui/chat-ui.component';
import { ChatUiMessageComponent } from './chat-ui/chat-ui-message/chat-ui-message.component';
import { SettingsComponent } from './settings/settings.component';
import { MetricsComponent } from './metrics/metrics.component';
import { StatusBarComponent } from './status-bar/status-bar.component';
import { AuthCallbackComponent } from './auth/auth-callback/auth-callback.component';
import { AuthGuard } from './auth/auth.guard';
import { LoginComponent } from './login/login.component';
import { ChatUiInputfieldComponent } from './chat-ui/chat-ui-inputfield/chat-ui-inputfield.component';
import { AudioMessageComponent } from './components/audio-message/audio-message.component';

// Services
import { AuthService } from './auth/auth.service';
import { ConversationComponent } from './sidebar/conversation/conversation.component';


// Angular Material
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatCardModule } from '@angular/material/card';
import { MatDialogModule } from '@angular/material/dialog';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';

// Default
import { inject, isDevMode, NgModule, provideAppInitializer } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppComponent } from './app.component';
import { ServiceWorkerModule } from '@angular/service-worker';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { provideHttpClient, withInterceptorsFromDi, HTTP_INTERCEPTORS, HttpClient } from '@angular/common/http';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { RouterModule, Routes } from '@angular/router';
import { SidebarComponent } from "./sidebar/sidebar.component";
import { CommonModule } from '@angular/common';
import { AuthInterceptor } from './auth/auth.interceptor';
import { TranslateLoader, TranslateModule } from "@ngx-translate/core";
import { TranslateHttpLoader } from "@ngx-translate/http-loader";
import { MarkdownModule, MARKED_OPTIONS } from 'ngx-markdown';


// Routes
const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: '', component: ChatUiComponent, canActivate: [AuthGuard] },
  { path: 'metrics', component: MetricsComponent, canActivate: [AuthGuard] },
  { path: 'settings', component: SettingsComponent, canActivate: [AuthGuard] },
  { path: 'auth/callback', component: AuthCallbackComponent },
];

export function HttpLoaderFactory(http: HttpClient) {
  return new TranslateHttpLoader(http, './assets/i18n/', '.json');
}

@NgModule({
  declarations: [
    AppComponent,
    ChatUiComponent,
    ChatUiMessageComponent,
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
    MatCardModule,
    MatDialogModule,
    MatExpansionModule,
    MatTooltipModule,
    MatMenuModule,
    CommonModule,
    ChatUiInputfieldComponent,
    RouterModule.forRoot(routes),
    ServiceWorkerModule.register(
      'ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000'
    }),
    BrowserAnimationsModule,
    SidebarComponent,
    ConversationComponent,
    SettingsComponent,
    AudioMessageComponent,
    TranslateModule.forRoot({
      loader: {
        provide: TranslateLoader,
        useFactory: HttpLoaderFactory,
        deps: [HttpClient]
      }
    }),
    MarkdownModule.forRoot({
      markedOptions: {
        provide: MARKED_OPTIONS,
        useValue: {
          gfm: true,
          breaks: true,
        },
      },
    })
  ],
  providers: [
    provideHttpClient(withInterceptorsFromDi()),
    {
      provide: HTTP_INTERCEPTORS,
      useClass: AuthInterceptor,
      multi: true
    },
    provideAppInitializer(() => {
      const authService = inject(AuthService);
      return authService.initializeAuth();
    })
  ]
})
export class AppModule {
}

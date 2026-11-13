import { Injectable } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';
import { FamilyModeService } from './family-mode.service';

/**
 * Tells the backend that this device is in family mode: every request to it
 * carries X-Family-Mode: 1 while the switch "Show hidden content" is off. The streamed answers
 * (fetch, not HttpClient) add the header in StreamingService.
 */
@Injectable()
export class FamilyModeInterceptor implements HttpInterceptor {
  constructor(private familyMode: FamilyModeService) {}

  intercept(req: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {
    if (!this.familyMode.active || !req.url.startsWith(environment.apiUrl)) {
      return next.handle(req);
    }
    return next.handle(req.clone({ headers: req.headers.set(FamilyModeService.HEADER, '1') }));
  }
}

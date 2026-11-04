import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

/** Only signed-in users (not guests) may open pages with data of their own, like the knowledge base. */
export const memberGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  await authService.initializeAuth();
  return authService.isAuthenticated() && !authService.isGuest ? true : router.createUrlTree(['/login']);
};

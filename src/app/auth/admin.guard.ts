import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

/** Only catalog admins (GET /api/auth/me isAdmin) may open the catalog management page. */
export const adminGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  await authService.initializeAuth();
  return authService.isAdmin ? true : router.createUrlTree(['/']);
};

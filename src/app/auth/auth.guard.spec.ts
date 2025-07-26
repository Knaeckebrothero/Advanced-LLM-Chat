import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import { AuthGuard } from './auth.guard';
import { AuthService } from './auth.service';
import { BehaviorSubject } from 'rxjs';

describe('AuthGuard', () => {
  let guard: AuthGuard;
  let authService: AuthService;
  let router: Router;
  let mockCurrentUserSubject: BehaviorSubject<any>;

  beforeEach(() => {
    mockCurrentUserSubject = new BehaviorSubject<any>(null);

    const authServiceMock = {
      currentUser$: mockCurrentUserSubject.asObservable()
    };

    const routerMock = {
      createUrlTree: jasmine.createSpy('createUrlTree').and.returnValue({} as UrlTree)
    };

    TestBed.configureTestingModule({
      providers: [
        AuthGuard,
        { provide: AuthService, useValue: authServiceMock },
        { provide: Router, useValue: routerMock }
      ]
    });

    guard = TestBed.inject(AuthGuard);
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  it('should be created', () => {
    expect(guard).toBeTruthy();
  });

  it('should allow access when user is authenticated', (done) => {
    const mockUser = { id: 1, email: 'test@example.com', name: 'Test User' };
    mockCurrentUserSubject.next(mockUser);

    guard.canActivate().subscribe(result => {
      expect(result).toBe(true);
      expect(router.createUrlTree).not.toHaveBeenCalled();
      done();
    });
  });

  it('should allow access when guest user is present', (done) => {
    const mockGuestUser = { id: 0, email: 'guest@example.com', name: 'Guest' };
    mockCurrentUserSubject.next(mockGuestUser);

    guard.canActivate().subscribe(result => {
      expect(result).toBe(true);
      expect(router.createUrlTree).not.toHaveBeenCalled();
      done();
    });
  });

  it('should redirect to login when no user is present', (done) => {
    mockCurrentUserSubject.next(null);

    guard.canActivate().subscribe(result => {
      expect(result).not.toBe(true);
      expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
      done();
    });
  });

  it('should handle undefined user by redirecting to login', (done) => {
    mockCurrentUserSubject.next(undefined);

    guard.canActivate().subscribe(result => {
      expect(result).not.toBe(true);
      expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
      done();
    });
  });
});
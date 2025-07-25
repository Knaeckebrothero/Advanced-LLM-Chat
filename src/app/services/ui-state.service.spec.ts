import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { UIStateService, UIState } from './ui-state.service';
import { first } from 'rxjs/operators';

describe('UIStateService', () => {
  let service: UIStateService;
  let originalInnerWidth: number;
  let originalInnerHeight: number;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(UIStateService);
    
    // Store original values
    originalInnerWidth = window.innerWidth;
    originalInnerHeight = window.innerHeight;
  });

  afterEach(() => {
    // Restore original values
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: originalInnerWidth
    });
    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: originalInnerHeight
    });
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('Sidebar Management', () => {
    it('should start with sidebar open', (done) => {
      service.sidebarOpen$.subscribe(isOpen => {
        expect(isOpen).toBe(true);
        done();
      });
    });

    it('should toggle sidebar state', (done) => {
      service.toggleSidebar();
      service.sidebarOpen$.subscribe(isOpen => {
        expect(isOpen).toBe(false);
        done();
      });
    });

    it('should open sidebar', (done) => {
      service.closeSidebar();
      service.openSidebar();
      service.sidebarOpen$.subscribe(isOpen => {
        expect(isOpen).toBe(true);
        done();
      });
    });

    it('should close sidebar', (done) => {
      service.openSidebar();
      service.closeSidebar();
      service.sidebarOpen$.subscribe(isOpen => {
        expect(isOpen).toBe(false);
        done();
      });
    });

    it('should close sidebar on mobile when closeSidebarOnMobile is called', () => {
      // Set viewport to mobile size
      setViewportSize(500, 800);
      service.openSidebar();
      service.closeSidebarOnMobile();
      expect(service.isSidebarOpen).toBe(false);
    });

    it('should not close sidebar on desktop when closeSidebarOnMobile is called', () => {
      // Set viewport to desktop size
      setViewportSize(1400, 900);
      service.openSidebar();
      service.closeSidebarOnMobile();
      expect(service.isSidebarOpen).toBe(true);
    });
  });

  describe('Responsive State', () => {
    it('should detect mobile viewport', (done) => {
      setViewportSize(500, 800);
      // Trigger resize event
      window.dispatchEvent(new Event('resize'));
      
      setTimeout(() => {
        service.isMobile$.subscribe(isMobile => {
          expect(isMobile).toBe(true);
          done();
        });
      }, 150); // Wait for debounce
    });

    it('should detect tablet viewport', (done) => {
      setViewportSize(900, 800);
      window.dispatchEvent(new Event('resize'));
      
      setTimeout(() => {
        service.isTablet$.subscribe(isTablet => {
          expect(isTablet).toBe(true);
          done();
        });
      }, 150);
    });

    it('should detect desktop viewport', (done) => {
      setViewportSize(1400, 900);
      window.dispatchEvent(new Event('resize'));
      
      setTimeout(() => {
        service.isDesktop$.subscribe(isDesktop => {
          expect(isDesktop).toBe(true);
          done();
        });
      }, 150);
    });

    it('should provide synchronous getters', () => {
      setViewportSize(500, 800);
      expect(service.isMobile).toBe(true);
      
      setViewportSize(900, 800);
      expect(service.isTablet()).toBe(true);
      
      setViewportSize(1400, 900);
      expect(service.isDesktop()).toBe(true);
    });
  });

  describe('Active Conversation', () => {
    it('should start with no active conversation', (done) => {
      service.activeConversationId$.subscribe(id => {
        expect(id).toBeNull();
        done();
      });
    });

    it('should set active conversation', (done) => {
      service.setActiveConversation('123');
      service.activeConversationId$.subscribe(id => {
        expect(id).toBe('123');
        done();
      });
    });

    it('should clear active conversation', (done) => {
      service.setActiveConversation('123');
      service.setActiveConversation(null);
      service.activeConversationId$.subscribe(id => {
        expect(id).toBeNull();
        done();
      });
    });
  });

  describe('Combined State', () => {
    it('should provide complete UI state', (done) => {
      setViewportSize(500, 800);
      service.setActiveConversation('123');
      service.closeSidebar();
      
      service.state$.pipe(first()).subscribe(state => {
        expect(state).toEqual(jasmine.objectContaining({
          isSidebarOpen: false,
          isMobile: true,
          isTablet: false,
          isDesktop: false,
          viewportWidth: 500,
          viewportHeight: 800,
          activeConversationId: '123'
        }));
        done();
      });
    });

    it('should provide current state synchronously', () => {
      setViewportSize(1400, 900);
      service.setActiveConversation('456');
      service.openSidebar();
      
      const state = service.getCurrentState();
      expect(state).toEqual(jasmine.objectContaining({
        isSidebarOpen: true,
        isMobile: false,
        isTablet: false,
        isDesktop: true,
        viewportWidth: 1400,
        viewportHeight: 900,
        activeConversationId: 'conv-456'
      }));
    });
  });

  describe('Custom Breakpoints', () => {
    it('should allow custom breakpoint configuration', fakeAsync(() => {
      service.setBreakpoints({ mobile: 600, tablet: 900 });
      setViewportSize(650, 800);
      
      tick(150); // Wait for debounce
      
      service.isMobile$.subscribe(isMobile => {
        expect(isMobile).toBe(false); // 650 > 600
      });
      
      service.isTablet$.subscribe(isTablet => {
        expect(isTablet).toBe(true); // 650 between 600 and 900
      });
    }));
  });

  describe('Auto Sidebar Behavior', () => {
    it('should auto-close sidebar on mobile resize', fakeAsync(() => {
      setViewportSize(1400, 900);
      service.openSidebar();
      
      // Resize to mobile
      setViewportSize(500, 800);
      window.dispatchEvent(new Event('resize'));
      
      tick(150); // Wait for debounce
      
      expect(service.isSidebarOpen).toBe(false);
    }));

    it('should auto-open sidebar on desktop resize', fakeAsync(() => {
      setViewportSize(500, 800);
      service.closeSidebar();
      
      // Resize to desktop
      setViewportSize(1400, 900);
      window.dispatchEvent(new Event('resize'));
      
      tick(150); // Wait for debounce
      
      expect(service.isSidebarOpen).toBe(true);
    }));
  });

  // Helper function to set viewport size
  function setViewportSize(width: number, height: number): void {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: width
    });
    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: height
    });
  }
});
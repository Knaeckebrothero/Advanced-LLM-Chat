import { Component, ElementRef, ViewChild, NgZone } from '@angular/core';
import { StatusBarService } from './status-bar/status-bar.service';


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  @ViewChild('swipeArea') swipeArea!: ElementRef;

  title = 'Advanced LLM Chat';
  private touchStartX = 0;
  private touchEndX = 0;

  constructor(private statusService: StatusBarService, private zone: NgZone) { }

  ngAfterViewInit() {
    this.addSwipeListeners();
  }

  toggleNavbar() {
    this.statusService.toggleSidenav();
  }

  addSwipeListeners() {
    this.zone.runOutsideAngular(() => {
      const swipeElement = this.swipeArea.nativeElement;

      swipeElement.addEventListener('touchstart', (event: TouchEvent) => {
        this.touchStartX = event.touches[0].clientX;
      }, { passive: true });

      swipeElement.addEventListener('touchmove', (event: TouchEvent) => {
        this.touchEndX = event.touches[0].clientX;
      }, { passive: true });

      swipeElement.addEventListener('touchend', () => {
        if (this.touchStartX < this.touchEndX && Math.abs(this.touchStartX - this.touchEndX) > 50) {
          // A right swipe gesture was detected
          this.zone.run(() => {
            this.toggleNavbar();
          });
        }
      }, { passive: true });
    });
  }
}

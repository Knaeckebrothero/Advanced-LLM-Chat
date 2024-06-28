import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ChatUiComponent } from './chat-ui.component';

describe('ChatUiComponent', () => {
  let component: ChatUiComponent;
  let fixture: ComponentFixture<ChatUiComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      declarations: [ChatUiComponent]
    });
    fixture = TestBed.createComponent(ChatUiComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

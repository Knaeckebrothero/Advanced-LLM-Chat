import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ChatUiMessageComponent } from './chat-ui-message.component';

describe('ChatUiMessageComponent', () => {
  let component: ChatUiMessageComponent;
  let fixture: ComponentFixture<ChatUiMessageComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      declarations: [ChatUiMessageComponent]
    });
    fixture = TestBed.createComponent(ChatUiMessageComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

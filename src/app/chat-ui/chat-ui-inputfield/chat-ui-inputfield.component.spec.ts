import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { ChatUiInputfieldComponent } from './chat-ui-inputfield.component';


describe('ChatUiInputfieldComponent', () => {
  let component: ChatUiInputfieldComponent;
  let fixture: ComponentFixture<ChatUiInputfieldComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        ChatUiInputfieldComponent,
        FormsModule,
        MatIconModule,
        MatButtonModule
      ]
    })
      .compileComponents();

    fixture = TestBed.createComponent(ChatUiInputfieldComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should emit messageSent event when sending a message', () => {
    spyOn(component.messageSent, 'emit');
    component.messageText = 'Test message';
    component.sendMessage();

    expect(component.messageSent.emit).toHaveBeenCalledWith('Test message');
    expect(component.messageText).toBe('');
  });

  it('should show send button when there is content', () => {
    component.messageText = 'Some text';
    expect(component.hasContent).toBe(true);
  });

  it('should show mic button when input is empty', () => {
    component.messageText = '';
    expect(component.hasContent).toBe(false);
  });
});

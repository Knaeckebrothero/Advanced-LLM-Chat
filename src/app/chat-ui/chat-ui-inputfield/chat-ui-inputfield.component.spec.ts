import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
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
        MatButtonModule,
        MatMenuModule,
        MatTooltipModule,
        BrowserAnimationsModule
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

  it('should check device capabilities on init', () => {
    spyOn<any>(component, 'checkDeviceCapabilities');
    component.ngOnInit();
    expect(component['checkDeviceCapabilities']).toHaveBeenCalled();
  });

  it('should emit cameraRequested event when camera is clicked', () => {
    spyOn(component.cameraRequested, 'emit');
    component.handleCameraClick();
    expect(component.cameraRequested.emit).toHaveBeenCalled();
  });

  it('should emit locationRequested event when location is clicked', () => {
    spyOn(component.locationRequested, 'emit');
    component.handleLocationClick();
    expect(component.locationRequested.emit).toHaveBeenCalled();
  });

  it('should emit fileRequested event when files are selected', () => {
    spyOn(component.fileRequested, 'emit');
    const mockFiles = [new File([''], 'test.txt')];
    const mockEvent = {
      target: {
        files: mockFiles
      }
    } as any;

    component.handleFileSelection(mockEvent);
    expect(component.fileRequested.emit).toHaveBeenCalledWith(mockFiles);
  });

  it('should handle Enter key to send message', () => {
    spyOn(component, 'sendMessage');
    const event = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: false });
    component.messageText = 'Test message';

    component.handleKeyPress(event);
    expect(component.sendMessage).toHaveBeenCalled();
  });

  it('should not send message on Shift+Enter', () => {
    spyOn(component, 'sendMessage');
    const event = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true });

    component.handleKeyPress(event);
    expect(component.sendMessage).not.toHaveBeenCalled();
  });
});

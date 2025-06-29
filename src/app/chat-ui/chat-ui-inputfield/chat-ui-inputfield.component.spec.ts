import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ChatUiInputfieldComponent } from './chat-ui-inputfield.component';
import { FilePreview, FileType, UploadStatus } from '../../data/objects/file-preview';
import { DeviceCapabilitiesService } from '../services/device-capabilities.service';
import { VoiceRecordingService } from './voice-recording.service';
import { FileHandlingService } from '../services/file-handling.service';
import { of } from 'rxjs';


describe('ChatUiInputfieldComponent', () => {
  let component: ChatUiInputfieldComponent;
  let fixture: ComponentFixture<ChatUiInputfieldComponent>;
  let deviceCapabilitiesServiceMock: jasmine.SpyObj<DeviceCapabilitiesService>;
  let voiceRecordingServiceMock: jasmine.SpyObj<VoiceRecordingService>;
  let fileHandlingServiceMock: jasmine.SpyObj<FileHandlingService>;

  beforeEach(async () => {
    // Create mock services
    deviceCapabilitiesServiceMock = jasmine.createSpyObj('DeviceCapabilitiesService', ['getCapabilities']);
    voiceRecordingServiceMock = jasmine.createSpyObj('VoiceRecordingService',
      ['getRecordingState', 'startRecording', 'stopRecording', 'cancelRecording']);
    fileHandlingServiceMock = jasmine.createSpyObj('FileHandlingService',
      ['validateFileSize', 'createFilePreviews', 'createAudioFilePreview', 'getFileIcon']);

    // Configure mock behavior
    deviceCapabilitiesServiceMock.getCapabilities.and.returnValue(of({
      hasCamera: true,
      hasMultipleCameras: false,
      hasGeolocation: true,
      hasAudioInput: true,
      isMobile: false
    }));

    voiceRecordingServiceMock.getRecordingState.and.returnValue(of({
      isRecording: false,
      duration: 0,
      audioLevel: 0
    }));

    fileHandlingServiceMock.validateFileSize.and.returnValue(true);
    fileHandlingServiceMock.getFileIcon.and.returnValue('description');

    await TestBed.configureTestingModule({
      imports: [
        ChatUiInputfieldComponent,
        FormsModule,
        MatIconModule,
        MatButtonModule,
        MatMenuModule,
        MatTooltipModule,
        BrowserAnimationsModule
      ],
      providers: [
        { provide: DeviceCapabilitiesService, useValue: deviceCapabilitiesServiceMock },
        { provide: VoiceRecordingService, useValue: voiceRecordingServiceMock },
        { provide: FileHandlingService, useValue: fileHandlingServiceMock }
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

  it('should subscribe to device capabilities on init', () => {
    component.ngOnInit();
    expect(deviceCapabilitiesServiceMock.getCapabilities).toHaveBeenCalled();
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

  it('should emit filesSelected event when files are selected', async () => {
    spyOn(component.filesSelected, 'emit');
    const mockFile = new File(['test content'], 'test.txt', { type: 'text/plain' });
    const mockEvent = {
      target: {
        files: [mockFile],
        value: ''
      }
    } as any;

    // Mock the createFilePreviews method to return a file preview
    const mockFilePreview: FilePreview = {
      id: 'test-id',
      file: mockFile,
      name: 'test.txt',
      size: 12,
      sizeFormatted: '12 Bytes',
      type: FileType.DOCUMENT,
      mimeType: 'text/plain',
      uploadStatus: UploadStatus.PENDING
    };
    fileHandlingServiceMock.createFilePreviews.and.returnValue(Promise.resolve([mockFilePreview]));

    await component.handleFileSelection(mockEvent);

    expect(fileHandlingServiceMock.validateFileSize).toHaveBeenCalled();
    expect(fileHandlingServiceMock.createFilePreviews).toHaveBeenCalled();
    expect(component.filesSelected.emit).toHaveBeenCalled();
    expect(component.filePreviews.length).toBe(1);
    expect(component.filePreviews[0].name).toBe('test.txt');
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

  it('should remove file preview when removeFilePreview is called', () => {
    // Add some test file previews
    component.filePreviews = [
      {
        id: 'file-1',
        file: new File([''], 'test1.txt'),
        name: 'test1.txt',
        size: 100,
        sizeFormatted: '100 Bytes',
        type: FileType.DOCUMENT,
        mimeType: 'text/plain',
        uploadStatus: UploadStatus.PENDING
      },
      {
        id: 'file-2',
        file: new File([''], 'test2.txt'),
        name: 'test2.txt',
        size: 200,
        sizeFormatted: '200 Bytes',
        type: FileType.DOCUMENT,
        mimeType: 'text/plain',
        uploadStatus: UploadStatus.PENDING
      }
    ];

    component.removeFilePreview('file-1');

    expect(component.filePreviews.length).toBe(1);
    expect(component.filePreviews[0].id).toBe('file-2');
  });

  it('should use voice recording service when starting recording', async () => {
    // Mock the ElementRef for the canvas
    component['waveformCanvas'] = {
      nativeElement: document.createElement('canvas')
    } as any;

    // Call the private method directly
    await (component as any).beginRecording();

    // Verify the service was called with the correct parameters
    expect(voiceRecordingServiceMock.startRecording).toHaveBeenCalled();
    // Check that the first parameter is a RecordingConfig object
    const config = voiceRecordingServiceMock.startRecording.calls.mostRecent().args[0];
    expect(config.isHoldToRecord).toBe(component.isHoldToRecord);
    expect(config.maxDuration).toBe(300);
    expect(config.audioConstraints).toBeDefined();
  });

  it('should use voice recording service when stopping recording', async () => {
    // Mock the recording result
    const mockBlob = new Blob(['test'], { type: 'audio/webm' });
    const mockResult = {
      blob: mockBlob,
      duration: 10,
      mimeType: 'audio/webm'
    };
    voiceRecordingServiceMock.stopRecording.and.returnValue(Promise.resolve(mockResult));

    // Mock the file preview
    const mockFilePreview: FilePreview = {
      id: 'audio-1',
      file: new File([mockBlob], 'voice-message.webm'),
      name: 'Voice message (00:10)',
      size: 4,
      sizeFormatted: '4 Bytes',
      type: FileType.AUDIO,
      mimeType: 'audio/webm',
      uploadStatus: UploadStatus.PENDING
    };
    fileHandlingServiceMock.createAudioFilePreview.and.returnValue(mockFilePreview);

    // Call the method
    await component.sendVoiceMessage();

    // Verify the services were called
    expect(voiceRecordingServiceMock.stopRecording).toHaveBeenCalled();
    expect(fileHandlingServiceMock.createAudioFilePreview).toHaveBeenCalledWith(mockResult);
    expect(component.filePreviews).toContain(mockFilePreview);
  });
});

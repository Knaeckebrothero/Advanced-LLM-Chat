import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { FilePreview } from '../data/objects/file-preview';
import { CameraCaptureDialogComponent } from './camera-capture-dialog/camera-capture-dialog.component';


@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements AfterViewChecked {
  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Variables
  userName: string = 'user';
  aiName: string = 'Assistant';
  conversationId: number = 1;
  pendingFiles: FilePreview[] = [];

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Messages are managed by the ChatService and are passed to this component via observable.
  messages = this.chatService.messages;

  // Constructor
  constructor(
    private chatService: ChatService,
    private dialog: MatDialog
  ) {}

  // Method to scroll to the bottom of the chat window.
  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }
  // TODO: Do we want to move this to the app.component or combine it with device capabilities service!?

  // TODO: Deprecated check if this is still needed
  // Function to handle Enter key in textarea
  handleEnterKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      if (this.isMobileDevice()) {
        // It's a mobile device, allow line breaks on Enter
        event.preventDefault(); // This line might be removed if you want to allow new lines
      } else {
        // It's not a mobile device, send the message
        this.inputUserMessage();
        event.preventDefault(); // Prevents new line even on desktop after sending message
      }
    }
  }

  // TODO: Deprecated!
  // The addMessage method is called when the user submits a new message.
  inputUserMessage() {
    // The inputField property is checked to ensure that it is not empty.
    if (this.inputField !== '') {
      // The ChatService is used to add a new usermessage to the history.
      this.chatService.sendMessage(this.inputField);
      console.log('User added message:');

      this.scrollToBottom();

      // The input field is cleared.
      this.inputField = '';
    }
  }

  // TODO: Deprecated, this should be merged with the onMessageSent method!
  // Generate a new message
  async generateMessage(): Promise<void> {
    try {
      await this.chatService.generateMessage(this.aiName);
    } catch (error) {
      console.error('Error generating AI response:', error);
      // Optionally show an error to the user
    }
  }

  // Handle message sent from the input component
  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        // Log files for demo purposes
        if (this.pendingFiles.length > 0) {
          console.log('Message sent with files:', this.pendingFiles);
        }

        // Wait for the message to be sent (and conversation created if needed)
        await this.chatService.sendMessage(message);
        console.log('User added message:', message);
        this.scrollToBottom();

        // Clear pending files after sending
        this.pendingFiles = [];

        // Generate AI response after message is confirmed sent
        await this.generateMessage();
      } catch (error) {
        console.error('Error sending message:', error);
        // TODO: Optionally show an error to the user
      }
    }
  }

  // Handle audio recording request
  onAudioRequested(): void {
    console.log('Audio recording requested');
    // The voice recording is now handled internally by the input field component
    // This method is called when using tap-to-record mode
    // The component will handle the recording UI and create an audio file preview
    // which will be added to the files list automatically
  }

  // Handle file attachment request
  onFileRequested(filePreviews: FilePreview[]): void {
    console.log('Files selected:', filePreviews);
    // Store files temporarily until message is sent
    this.pendingFiles = filePreviews;
  }

  onCameraRequested(): void {
    console.log('Camera access requested');

    // Open the camera capture dialog
    const dialogRef = this.dialog.open(CameraCaptureDialogComponent, {
      width: '90vw',
      maxWidth: '600px',
      height: '80vh',
      panelClass: 'camera-capture-dialog-panel', // More specific class name
      disableClose: false,
      // Add these for better camera dialog styling
      hasBackdrop: true,
      backdropClass: 'camera-capture-backdrop'
    });

    // Handle the result
    dialogRef.afterClosed().subscribe((result: FilePreview | undefined) => {
      if (result) {
        // Add the captured photo to pending files
        this.pendingFiles = [...this.pendingFiles, result];
        console.log('Photo captured and added to files:', result);

        // Notify the input field component about the new file
        // This is a bit of a workaround, but we need to pass the files back
        // In a real implementation, you might want to use a service or state management
        this.onFileRequested(this.pendingFiles);
      }
    });
  }

  onLocationRequested(): void {
    console.log('Location sharing requested');
    // TODO: Get and display current location
  }

  /*

  // The inputSystemMessage method is called to add a new system message
  inputSystemMessage(messageId: number) {
    // The ChatService is used to add a new system message to the history.
    this.chatService.systemAddMessage(messageId);
  }

  */

  // Method to delete a message
  deleteMessage(messageId: number) {
    // Call the ChatService to delete the message
    this.chatService.deleteMessage(messageId);
  }

  // Method to change a message
  patchMessage(message: Message) {
    // Call the ChatService to alter the message
    this.chatService.patchMessage(message.id!, "New message content");
  }
}

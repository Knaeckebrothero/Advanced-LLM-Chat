import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';
import { CameraCaptureDialogComponent } from './camera-capture-dialog.component';


describe('CameraCaptureDialogComponent', () => {
  let component: CameraCaptureDialogComponent;
  let fixture: ComponentFixture<CameraCaptureDialogComponent>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<CameraCaptureDialogComponent>>;

  beforeEach(async () => {
    mockDialogRef = jasmine.createSpyObj(['close']);

    await TestBed.configureTestingModule({
      imports: [CameraCaptureDialogComponent],
      providers: [
        { provide: MatDialogRef, useValue: mockDialogRef }
      ]
    })
      .compileComponents();

    fixture = TestBed.createComponent(CameraCaptureDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should close dialog when cancel is called', () => {
    component.cancel();
    expect(mockDialogRef.close).toHaveBeenCalled();
  });

  it('should stop camera on destroy', () => {
    spyOn<any>(component, 'stopCamera');
    component.ngOnDestroy();
    expect(component['stopCamera']).toHaveBeenCalled();
  });
});

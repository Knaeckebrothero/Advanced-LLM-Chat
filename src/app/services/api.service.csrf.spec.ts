import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ApiService } from './api.service';
import { HttpHeaders, HttpResponse } from '@angular/common/http';

describe('ApiService - CSRF Protection', () => {
  let service: ApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ApiService]
    });
    service = TestBed.inject(ApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should extract CSRF token from response headers', () => {
    const mockCsrfToken = 'test-csrf-token-12345';
    const mockResponse = new HttpResponse({
      body: { data: 'test' },
      headers: new HttpHeaders({
        'X-CSRF-Token': mockCsrfToken
      })
    });

    // Extract CSRF token
    service.extractCsrfToken(mockResponse);

    // Verify token was stored (we need to access private property for testing)
    expect((service as any).csrfToken).toBe(mockCsrfToken);
  });

  it('should include CSRF token in request headers', async () => {
    const mockCsrfToken = 'test-csrf-token-12345';

    // Set CSRF token
    (service as any).csrfToken = mockCsrfToken;

    // Make a request that would trigger CSRF token inclusion
    const promise = service.getSettings();

    // Expect the request
    const req = httpMock.expectOne(req => req.url.includes('/api/settings'));

    // Verify CSRF token is in headers
    expect(req.request.headers.get('X-CSRF-Token')).toBe(mockCsrfToken);
    expect(req.request.headers.get('Content-Type')).toBe('application/json');
    expect(req.request.withCredentials).toBe(true);

    // Respond to complete the request
    req.flush({ theme: 'light', language: 'en' });

    await promise;
  });

  it('should handle responses without CSRF token gracefully', () => {
    const mockResponse = new HttpResponse({
      body: { data: 'test' },
      headers: new HttpHeaders({})
    });

    // Store initial token
    const initialToken = (service as any).csrfToken;

    // Extract CSRF token (should not change)
    service.extractCsrfToken(mockResponse);

    // Verify token unchanged
    expect((service as any).csrfToken).toBe(initialToken);
  });

  it('should update CSRF token when new one is received', () => {
    const firstToken = 'first-token';
    const secondToken = 'second-token';

    // Set first token
    const firstResponse = new HttpResponse({
      headers: new HttpHeaders({ 'X-CSRF-Token': firstToken })
    });
    service.extractCsrfToken(firstResponse);
    expect((service as any).csrfToken).toBe(firstToken);

    // Update with second token
    const secondResponse = new HttpResponse({
      headers: new HttpHeaders({ 'X-CSRF-Token': secondToken })
    });
    service.extractCsrfToken(secondResponse);
    expect((service as any).csrfToken).toBe(secondToken);
  });

  it('should extract CSRF token from getConversations response', async () => {
    const mockCsrfToken = 'conversations-csrf-token';
    const mockConversations = [
      { id: '1', name: 'Test Conv', participants: ['user', 'assistant'] }
    ];

    // Make the request
    const promise = service.getConversations();

    // Expect the request
    const req = httpMock.expectOne(req => req.url.includes('/api/conversations'));

    // Respond with CSRF token in headers
    req.flush(mockConversations, {
      headers: { 'X-CSRF-Token': mockCsrfToken }
    });

    await promise;

    // Verify CSRF token was extracted
    expect((service as any).csrfToken).toBe(mockCsrfToken);
  });
});
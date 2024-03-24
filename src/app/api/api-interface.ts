import { HttpHeaders } from '@angular/common/http';

// Interface used as a base for the API classes
export interface ApiInterface {
    url: string;
    headers: HttpHeaders;
    body: any;
}

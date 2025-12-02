/**
 * User Data Models
 */

export interface IUser {
  id: number;
  accessToken: string;
  email: string;
  name: string;
}

export interface IUserSession {
  user: IUser;
  expiresAt: Date;
}

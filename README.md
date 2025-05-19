# Advanced LLM Chat

A modern, Angular-based chat application for interacting with large language models (LLMs). This project provides a responsive interface with real-time message updates, conversation persistence, and convenient navigation between chat, metrics, and settings.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Development](#development)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Features

- Real-time chat interface with LLM integration
- Message persistence and offline support via IndexedDB
- Responsive design that works on both desktop and mobile
- Analytics dashboard for tracking conversation metrics
- Settings panel for customization
- Progressive Web App (PWA) support

## Prerequisites

Before you begin, ensure you have the following installed:

- Node.js (v16.x or higher recommended)
- npm (v8.x or higher)
- Python 3.8+ (for backend mockup)
- Angular CLI Version 19 (`npm install -g @angular/cli`)

## Installation

### Backend Setup

The project includes a Python FastAPI backend mockup for development purposes.

#### 1. Create a Virtual Environment

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Create .env File

Create a `.env` file in the root directory with the following content:

```
DEV_CERTS=True
DB_PATH=chat.db
```
**Tip:** You can use the [.env.example](.env.example) file to do this.

#### 4. Run the Backend

The first time you run the backend, it will generate self-signed certificates for HTTPS:

```bash
# First run to generate certificates
python backend_mockup.py

# Then start the server with uvicorn
uvicorn backend_mockup:app --reload --host 0.0.0.0 --port 8443 --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem
```

**Important:** You'll need to visit `https://localhost:8443` in your browser and accept the security exception for the self-signed certificate.

### Frontend Setup

#### 1. Install Dependencies

```bash
# Navigate to the project directory
cd advanced-llm-chat

# Install required packages
npm install
```

#### 2. Configure Environment

Ensure the API URL in `src/app/environments/environment.ts` points to your running backend:

```typescript
export const environment = {
    production: false,
    apiUrl: 'https://localhost:8443'
};
```

#### 3. Start the Development Server

```bash
ng serve
```

The application will be available at `http://localhost:4200`.

## Development

### Working with Angular Components

The project is structured with the following key components:

- `ChatUiComponent` - Main chat interface
- `MetricsComponent` - Analytics dashboard
- `SettingsComponent` - User settings
- `StatusBarComponent` - Navigation between views

### Building for Production

```bash
ng build --configuration production
```

The build artifacts will be stored in the `dist/advanced-llm-chat` directory.

### Running Tests

```bash
ng test
```

## Usage

### Chat Interface

- Type a message in the input box and press Enter or click the "SND" button to send
- Click the "GEN" button to generate a response from the LLM
- Messages are automatically saved to both the local database and the backend

### Navigation

Use the status bar to navigate between:
- Chat interface (main view)
- Metrics dashboard
- Settings panel

## Troubleshooting

### CORS Issues

If you encounter CORS errors:
1. Ensure the backend server is running
2. Check that the CORS origins in `backend_mockup.py` include your frontend URL
3. Make sure you're using HTTPS for both frontend and backend

### Certificate Issues

For development with self-signed certificates:

**Windows:**
```bash
# Set environment variable to bypass certificate validation (DEVELOPMENT ONLY)
set NODE_TLS_REJECT_UNAUTHORIZED=0
```

**macOS/Linux:**
```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0
```

**Important:** Only use this setting in development, never in production.

### Database Connection Issues

If you encounter database issues:
1. Check that the SQLite database file has been created
2. Ensure your user has permission to read/write to the file
3. Try deleting the file to start fresh (all data will be lost)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE.txt) file for details.

## Contact

Project Link: [https://github.com/knaeckebrothero/advanced-llm-chat](https://github.com/knaeckebrothero/advanced-llm-chat)

[Github](https://github.com/Knaeckebrothero) <br>
[Mail](mailto:OverlyGenericAddress@pm.me) <br>

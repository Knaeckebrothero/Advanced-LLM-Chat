# Project Title

One Paragraph of project description goes here. Explain what the project is about, what it does, and the value it provides to users.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)
- [Acknowledgements](#acknowledgements)

## Installation

### Frontend

#### Setup Developement Backend Mockup
To simplify frontend development this repository includes a mockup backend written in Python.

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install the requirements
pip install -r requirements.txt

# Run the script first to generate the certificates if needed
# backend_mockup.py

# Start the development server
uvicorn backend_mockup:app --reload --host 0.0.0.0 --port 8443 --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem
```

You might need to visit the https://localhost:8443/ in your browser and add a security exception, when using the self signed dev certificates.

#### Setup Frontend
The frontend is built with Angular. Make sure you have Node.js and npm installed on your system.

1. Install Angular CLI globally if you haven't already:
```bash
npm install -g @angular/cli
```

2. Install project dependencies:
```bash
# Navigate to the project directory
cd frontend-directory

# Install dependencies
npm install
```

3. Start the development server:
```bash
ng serve
```

The application will be available at `http://localhost:4200` by default.

#### Development Dependencies
- Node.js (v16 or higher recommended)
- npm (comes with Node.js)
- Python 3.8 or higher
- Angular CLI (@latest)

#### Additional Commands
```bash
# Create a production build
ng build --production

# Run tests
ng test

# Check for package updates
npm outdated

# Update packages (careful with major version updates)
npm update
```

#### Common Issues
- If you encounter CORS issues, make sure the backend server is running and the CORS middleware is properly configured
- If npm install fails, try deleting the node_modules folder and package-lock.json, then run npm install again
- Make sure your Node.js version is compatible with the Angular version used in the project

### Backend

## License

This project is licensed under the terms of the Creative Commons Attribution 4.0 International License (CC BY 4.0) and the All Rights Reserved License. See the [LICENSE](LICENSE.txt) file for details.

## Contact
[Github](https://github.com/Knaeckebrothero) <br>
[Mail](mailto:OverlyGenericAddress@pm.me) <br>

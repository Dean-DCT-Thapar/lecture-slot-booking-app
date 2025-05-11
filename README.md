# EduTube Slot Booking Application

A web application for managing and booking time slots, with integration for Google Calendar.

## Features

- User Authentication (Admin/Teacher roles)
- Slot Management
  - Create slots (bulk/individual)
  - Delete slots
  - Toggle slot availability
- Booking System
  - View available slots
  - Book slots with description
  - Cancel bookings
- Google Calendar Integration
- Automatic cleanup of expired slots

## Technology Stack

- Backend: Python Flask
- Database: SQLite with SQLAlchemy ORM
- Frontend: HTML, CSS, JavaScript
- Authentication: Flask-Login
- Scheduling: APScheduler
- Calendar API: Google Calendar API

## Setup

1. Install required packages:
```bash
pip install flask flask-sqlalchemy flask-login google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client apscheduler
```

2. Set up Google Calendar API:
   - Place your `google_credentials.json` in the project root
   - Enable Google Calendar API in Google Cloud Console
   - Set up Service Account and download credentials

3. Initialize the database:
```python
from application.models import db
db.create_all()
```

4. Run the application:
```bash
python app.py
```

## Project Structure

```
slot booking app/
├── application/
│   └── models.py
├── static/
│   ├── styles.css
│   ├── admin_dashboard.css
│   ├── teacher_dashboard.css
│   └── [...other css files]
├── templates/
│   ├── login.html
│   ├── register.html
│   ├── admin_dashboard.html
│   ├── teacher_dashboard.html
│   └── [...other template files]
├── app.py
├── google_credentials.json
└── README.md
```

## Usage

### Admin Features
- Create slots in bulk or individually
- Manage slot availability
- View all bookings
- Delete slots

### Teacher Features
- View available slots
- Book slots with description
- Cancel own bookings
- View booking history

## Security Features

- Role-based access control
- Password authentication
- Secure session management
- CSRF protection

## Maintenance

The application includes automatic maintenance features:
- Daily cleanup of expired slots at midnight
- Automatic synchronization with Google Calendar

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
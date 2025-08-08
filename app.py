from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from application.models import db, User, Slot, Booking
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import date
import logging
from logging.handlers import RotatingFileHandler
from config import config

app = Flask(__name__)

# Load configuration based on environment
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

# Set up logging for production
if not app.debug and not app.testing:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler('logs/slot_booking.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Slot booking application startup')

# Security headers
@app.after_request
def after_request(response):
    # Security headers for production
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    if app.config.get('FORCE_HTTPS'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response

@app.template_filter('dayfromdate')
def dayfromdate(value):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime('%A')
    return value

current_dir = os.path.abspath(os.path.dirname(__file__))
db.init_app(app)

# Initialize Flask-Migrate
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    with db.session() as session:
        return session.get(User, int(user_id))

def delete_old_slots_job():
    """Background job to clean up old slots"""
    try:
        with app.app_context():
            today = datetime.today().date()
            old_slots = Slot.query.filter(Slot.slot_date < today).all()
            deleted_count = len(old_slots)
            
            for slot in old_slots:
                db.session.delete(slot)
            db.session.commit()
            
            app.logger.info(f"Deleted {deleted_count} old slot(s) before {today}.")
    except Exception as e:
        app.logger.error(f"Error in delete_old_slots_job: {str(e)}")
        db.session.rollback()

# Set up the scheduler to run the deletion job every day at midnight.
scheduler = BackgroundScheduler()

def initialize_scheduler():
    """Initialize the scheduler with database check"""
    # Skip scheduler initialization if requested
    if os.environ.get('SKIP_SCHEDULER') == 'true':
        app.logger.info("Skipping scheduler initialization")
        return
        
    try:
        if not scheduler.running:
            with app.app_context():
                # Only check if database is accessible
                try:
                    today = datetime.today().date()
                    old_slots_exist = Slot.query.filter(Slot.slot_date < today).count() > 0
                    if old_slots_exist:
                        app.logger.info("Found old slots, scheduling cleanup job")
                except Exception as db_error:
                    app.logger.warning(f"Could not check for old slots, will schedule cleanup anyway: {db_error}")
                
                scheduler.add_job(func=delete_old_slots_job, trigger="cron", hour=0, minute=0, id="cleanup_job")
                scheduler.start()
                app.logger.info("Background scheduler started")
    except Exception as e:
        app.logger.error(f"Failed to initialize scheduler: {e}")

def safe_shutdown_scheduler():
    """Safely shutdown the scheduler"""
    try:
        if scheduler.running:
            scheduler.shutdown()
            app.logger.info("Scheduler shutdown completed")
    except Exception as e:
        app.logger.error(f"Error during scheduler shutdown: {e}")

atexit.register(safe_shutdown_scheduler)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Input validation and sanitization
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip().lower()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        
        # Validate required fields
        if not all([username, password, email, first_name, last_name]):
            message = 'All fields are required.'
            return render_template('register.html', message=message)
        
        # Validate username format (alphanumeric and underscore only)
        import re
        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
            message = 'Username must be 3-20 characters long and contain only letters, numbers, and underscores.'
            return render_template('register.html', message=message)
        
        # Validate password strength
        if len(password) < 8:
            message = 'Password must be at least 8 characters long.'
            return render_template('register.html', message=message)
        
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            message = 'Please enter a valid email address.'
            return render_template('register.html', message=message)
        
        # Validate name fields
        if not re.match(r'^[a-zA-Z\s]{2,30}$', first_name):
            message = 'First name must be 2-30 characters long and contain only letters and spaces.'
            return render_template('register.html', message=message)
        
        if not re.match(r'^[a-zA-Z\s]{2,30}$', last_name):
            message = 'Last name must be 2-30 characters long and contain only letters and spaces.'
            return render_template('register.html', message=message)
        
        try:
            # Check if the username already exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                message = 'Username already exists. Please choose a different one.'
                return render_template('register.html', message=message)
            
            # Check if the email already exists
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                message = 'Email address already exists. Please use a different email.'
                return render_template('register.html', message=message)
            
            # Create new user with proper capitalization
            new_user = User(
                username=username, 
                password=password, 
                email=email, 
                first_name=first_name.title(), 
                last_name=last_name.title(), 
                role="teacher"
            )
            
            # Add the new user to the database
            db.session.add(new_user)
            db.session.commit()
            
            app.logger.info(f'New user registered: {username} ({email})')
            flash('User registered successfully!')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Registration error: {str(e)}')
            message = 'An error occurred during registration. Please try again.'
            return render_template('register.html', message=message)
    
    return render_template('register.html')

@app.route('/check_availability', methods=['POST'])
def check_availability():
    data = request.get_json()
    field = data.get('field')
    value = data.get('value')
    
    if not field or not value:
        return jsonify({'available': True})
    
    if field == 'username':
        existing = User.query.filter_by(username=value).first()
        return jsonify({'available': existing is None})
    elif field == 'email':
        existing = User.query.filter_by(email=value).first()
        return jsonify({'available': existing is None})
    
    return jsonify({'available': True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            if user.role == 'admin':
                delete_old_slots_job()
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('teacher_dashboard'))
        message = 'Invalid username or password'
        return render_template('login.html', message=message)
    return render_template('login.html')

# New route: Display available slots for the teacher for a selected date
@app.route('/teacher_slots', methods=['GET'])
@login_required
def teacher_slots():
    selected_date = request.args.get('date')
    today = date.today()
    # Show all days in the current year
    first_day = today.replace(month=1, day=1)
    last_day = today.replace(month=12, day=31)
    calendar_days = [first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)]

    # Find all dates with available slots
    slots_all = Slot.query.filter(Slot.available == True, ~Slot.bookings.any()).all()
    available_dates = {slot.slot_date.strftime('%Y-%m-%d') for slot in slots_all}

    slots = []
    if selected_date:
        date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
        slots = [slot for slot in slots_all if slot.slot_date == date_obj]

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' and selected_date:
        return render_template('slots_table.html', slots=slots, selected_date=selected_date)

    return render_template(
        'teacher_slots.html',
        calendar_days=calendar_days,
        available_dates=available_dates,
        selected_date=selected_date,
        slots=slots
    )

# Updated teacher dashboard to show the teacher's bookings
@app.route('/teacher')
@login_required
def teacher_dashboard():
    if current_user.role != "teacher":
        return redirect(url_for('login'))
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('teacher_dashboard.html', bookings=bookings,current_user=current_user, current_date=date.today())

@app.route('/admin/slots', methods=['GET'])
@login_required
def admin_slots():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    search_date_str = request.args.get('search_date', None)
    if search_date_str:
        try:
            search_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format!')
            search_date = None
    else:
        search_date = None

    if search_date:
        slots = Slot.query.filter(Slot.slot_date == search_date, Slot.available == True, ~Slot.bookings.any()).all()
    else:
        slots = Slot.query.filter(Slot.available == True, ~Slot.bookings.any()).all()

    return render_template('admin_slots.html', slots=slots, search_date=search_date_str)

@app.route('/admin/create_slot', methods=['GET'])
@login_required
def create_slot():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('create_slots.html')

# Admin route: Toggle a slot's availability
@app.route('/admin/slot_availability/<int:slot_id>', methods=['POST'])
@login_required
def set_slot_availability(slot_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied!'}), 403
    slot = Slot.query.get_or_404(slot_id)
    # Form field "available" is expected with value "true" or "false"
    new_status = request.form.get('available') == 'true'
    slot.available = new_status
    db.session.commit()
    # Return the updated status as JSON.
    return jsonify({'success': True, 'available': new_status})

# Update admin dashboard to list all bookings (optionally also display slots)
@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('login'))
    bookings = Booking.query.all()
    return render_template('admin_dashboard.html', bookings=bookings, current_user=current_user, current_date=date.today())

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    users = User.query.all()
    return render_template('admin_users.html', users=users, current_user=current_user, current_date=date.today())

@app.route('/book/<int:slot_id>', methods=['POST'])
@login_required
def book_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)
    existing_booking = Booking.query.filter_by(slot_id=slot.id).first()
    if not existing_booking and slot.available:
        usersearch = User.query.filter_by(id=current_user.id).first()
        description = request.form.get('description', 'None')
        metadata = {
            "username" : usersearch.username,
            "email" : usersearch.email,
            "full_name": f"{usersearch.first_name} {usersearch.last_name}",
            "description": description
        }
        event_id = add_event_to_calendar(slot,metadata)
        new_booking = Booking(user_id=current_user.id, slot_id=slot.id, event_id=event_id, description=description)
        db.session.add(new_booking)
        db.session.commit()
        flash('Slot booked and added to Google Calendar!')
    else:
        flash('Slot already booked or unavailable!')
    return render_template('booking_confirmation.html', slot=slot, description=description)

@app.route('/confirm_slot/<int:slot_id>', methods=['GET'])
@login_required
def confirm_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)
    if slot:
        return render_template('teacher_book_slot.html', slot=slot)
    else:
        flash('Slot not found!')

@app.route('/delete_booking/<int:booking_id>' , methods=['POST'])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    try:
        remove_event_from_calendar(booking.event_id)
    except Exception as e:
        print(f"Error removing event from Google Calendar: {e}")
    try:
        db.session.delete(booking)
        db.session.commit()
        print('Booking deleted and event removed from Google Calendar!')
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting booking: {e}")
        flash('An error occurred while deleting the booking.')
    
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    
    return redirect(url_for('teacher_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin/delete_slot', methods=['GET'])
@login_required
def delete_slots():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    search_date_str = request.args.get('search_date', None)
    if search_date_str:
        try:
            search_date = datetime.strptime(search_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format!')
            search_date = None
    else:
        search_date = None

    if search_date:
        slots = Slot.query.filter(Slot.slot_date == search_date, Slot.available == True, ~Slot.bookings.any()).all()
    else:
        slots = Slot.query.filter(Slot.available == True, ~Slot.bookings.any()).all()
        
    return render_template('delete_slots.html', slots=slots, search_date=search_date_str)


@app.route('/admin/create_bulk_slots', methods=['GET', 'POST'])
@login_required
def create_bulk_slots():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    if request.method == 'POST':
        # Get form data
        start_date_str = request.form.get('start_date')
        end_date_str   = request.form.get('end_date')
        start_time_str = request.form.get('start_time')
        end_time_str   = request.form.get('end_time')
        try:
            duration = int(request.form.get('duration'))
        except (ValueError, TypeError):
            flash('Invalid duration!')
            return redirect(url_for('create_bulk_slots'))
        excluded = request.form.getlist('exclude_days')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date   = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time   = datetime.strptime(end_time_str, '%H:%M').time()
        except ValueError:
            flash("Invalid date or time format.")
            return redirect(url_for('create_bulk_slots'))
        
        # Compute candidate dates (exclude the specified days)
        candidate_dates = []
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime('%A').lower()
            if day_name not in excluded:
                candidate_dates.append(current_date)
            current_date += timedelta(days=1)
        
        # For each candidate date, compute possible slots
        candidate_slots = []
        for cdate in candidate_dates:
            current_dt = datetime.combine(cdate, start_time)
            end_dt     = datetime.combine(cdate, end_time)
            slots_for_date = []
            while current_dt + timedelta(minutes=duration) <= end_dt:
                slot_start = current_dt.time()
                slot_end   = (current_dt + timedelta(minutes=duration)).time()
                slots_for_date.append({
                    'start': slot_start.strftime('%H:%M'),
                    'end': slot_end.strftime('%H:%M')
                })
                current_dt += timedelta(minutes=duration)
            if slots_for_date:
                candidate_slots.append({
                    'date': cdate.strftime('%Y-%m-%d'),
                    'slots': slots_for_date
                })
        
        # Render preview page with computed candidate_slots
        return render_template('admin_bulk_slots_preview.html',
                               candidate_slots=candidate_slots,
                               start_date=start_date_str,
                               end_date=end_date_str,
                               start_time=start_time_str,
                               end_time=end_time_str,
                               duration=duration,
                               excluded=excluded)
    
    return render_template('admin_create_bulk_slots.html')


@app.route('/admin/confirm_bulk_slots', methods=['POST'])
@login_required
def confirm_bulk_slots():
    if current_user.role != 'admin':
        flash('Permission denied!')
        return redirect(url_for('teacher_dashboard'))
    
    # Retrieve parameters (sent via hidden fields from the preview form)
    start_date_str = request.form.get('start_date')
    end_date_str   = request.form.get('end_date')
    start_time_str = request.form.get('start_time')
    end_time_str   = request.form.get('end_time')
    try:
        duration = int(request.form.get('duration'))
    except (ValueError, TypeError):
        flash('Invalid duration!')
        return redirect(url_for('create_bulk_slots'))
    excluded = request.form.getlist('excluded[]')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date   = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time   = datetime.strptime(end_time_str, '%H:%M').time()
    except ValueError:
        flash("Invalid date or time format.")
        return redirect(url_for('create_bulk_slots'))
    
    created_count = 0
    skipped_count = 0
    current_date = start_date
    while current_date <= end_date:
        day_name = current_date.strftime('%A').lower()
        if day_name not in excluded:
            current_dt = datetime.combine(current_date, start_time)
            end_dt     = datetime.combine(current_date, end_time)
            while current_dt + timedelta(minutes=duration) <= end_dt:
                slot_start = current_dt.time()
                slot_end   = (current_dt + timedelta(minutes=duration)).time()
                # Check if slot already exists
                existing_slot = Slot.query.filter_by(
                    slot_date=current_date,
                    slot_start_time=slot_start,
                    slot_end_time=slot_end
                ).first()
                if existing_slot:
                    skipped_count += 1
                else:
                    new_slot = Slot(
                        slot_date=current_date,
                        slot_start_time=slot_start,
                        slot_end_time=slot_end,
                        available=True
                    )
                    db.session.add(new_slot)
                    created_count += 1
                current_dt += timedelta(minutes=duration)
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'{created_count} slots created; {skipped_count} slots skipped because they already exist.')
    return redirect(url_for('admin_dashboard'))

#########################################################################
#                    Google Calendar API integration                    #
#########################################################################

def add_event_to_calendar(slot,metadata):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    print("Loading service account credentials...")
    credentials = service_account.Credentials.from_service_account_file(
        'credentials.json', scopes=SCOPES)
    print("Credentials loaded successfully. Building the Google Calendar service...")
    service = build('calendar', 'v3', credentials=credentials)

    start_dt = datetime.combine(slot.slot_date, slot.slot_start_time)
    end_dt = start_dt + timedelta(hours=1)
    print(f"Creating an event from {start_dt.isoformat()} to {end_dt.isoformat()}")

    event = {
        'summary': f'Name-{metadata["full_name"]}, Email-{metadata["email"]}, Description-{metadata["description"]}',  
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
    }
    print("Event details:", event)

    try:
        created_event = service.events().insert(calendarId='36b6b142b66921e3359c57c8134b2bdaf3e274e3cd5d6752677b6f8321bbaf70@group.calendar.google.com', body=event).execute()
        print("Google Calendar API response:", created_event)
        if created_event:
            print('Event successfully added to Google Calendar!')
            return created_event.get('id')
        else:
            print('Failed to add event to Google Calendar.')
        
    except Exception as e:
        print("Error occurred while adding event:", e)

def remove_event_from_calendar(event_id):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    credentials = service_account.Credentials.from_service_account_file(
        'credentials.json', scopes=SCOPES)
    service = build('calendar', 'v3', credentials=credentials)

    try:
        service.events().delete(calendarId='36b6b142b66921e3359c57c8134b2bdaf3e274e3cd5d6752677b6f8321bbaf70@group.calendar.google.com', eventId=event_id).execute()
        print('Event successfully removed from Google Calendar!')
    except Exception as e:
        print("Error occurred while removing event:", e)

@app.route('/admin/delete_slot/<int:slot_id>', methods=['POST'])
@login_required
def delete_slot(slot_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied!'}), 403
    
    slot = Slot.query.get_or_404(slot_id)
    db.session.delete(slot)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/admin/delete_slots_bulk', methods=['POST'])
@login_required
def delete_slots_bulk():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied!'}), 403
    
    slot_ids = request.json.get('slot_ids', [])
    if not slot_ids:
        return jsonify({'success': False, 'error': 'No slots selected!'}), 400
    
    try:
        deleted_count = 0
        for slot_id in slot_ids:
            slot = Slot.query.get(slot_id)
            if slot:
                db.session.delete(slot)
                deleted_count += 1
        
        db.session.commit()
        return jsonify({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Error handlers for production
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    app.logger.error(f'Server Error: {error}')
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

if __name__ == '__main__':
    # Initialize scheduler when running directly
    initialize_scheduler()
    
    # Only run in debug mode for development
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
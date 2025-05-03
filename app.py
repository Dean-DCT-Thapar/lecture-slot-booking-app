from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from application.models import db, User, Slot, Booking  # include Booking
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'

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
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///" + os.path.join(current_dir , "database/slots.db")
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    with db.session() as session:
        return session.get(User, int(user_id))

def delete_old_slots_job():
    with app.app_context():
        today = datetime.today().date()
        old_slots = Slot.query.filter(Slot.slot_date < today).all()
        for slot in old_slots:
            db.session.delete(slot)
        db.session.commit()
        print(f"Deleted {len(old_slots)} old slot(s) before {today}.")

# Set up the scheduler to run the deletion job every day at midnight
scheduler = BackgroundScheduler()
scheduler.add_job(func=delete_old_slots_job, trigger="cron", hour=0, minute=0)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username and password:
            new_user = User(username=username, password=password, role="teacher")
            # Check if the username already exists
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                message = 'Username already exists. Please choose a different one.'
                return render_template('register.html', message=message)
            # Add the new user to the database
            db.session.add(new_user)
            db.session.commit()
            flash('User registered successfully!')
            return redirect(url_for('login'))
        else:
            flash('Please fill in all fields.')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            if user.role == 'admin':
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
    slots = []
    if selected_date:
        date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
        # Only list slots for the given date that are marked available and not already booked
        slots = Slot.query.filter(
            Slot.slot_date == date_obj,
            Slot.available == True,
            ~Slot.bookings.any()  # Ensure the slot is not already booked
        ).all()
    return render_template('teacher_slots.html', slots=slots, selected_date=selected_date)

# Updated teacher dashboard to show the teacher's bookings
@app.route('/teacher')
@login_required
def teacher_dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('teacher_dashboard.html', bookings=bookings)

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
        slots = Slot.query.filter_by(slot_date=search_date).all()
    else:
        slots = Slot.query.all()
        
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
    bookings = Booking.query.all()
    return render_template('admin_dashboard.html', bookings=bookings)

@app.route('/book/<int:slot_id>', methods=['POST'])
@login_required
def book_slot(slot_id):
    slot = Slot.query.get_or_404(slot_id)
    existing_booking = Booking.query.filter_by(slot_id=slot.id).first()
    if not existing_booking and slot.available:
        event_id = add_event_to_calendar(slot)
        description = request.form.get('description', 'None')
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
    if booking.user_id == current_user.id:
        remove_event_from_calendar(booking.event_id)
        db.session.delete(booking)
        db.session.commit()
        print('Booking deleted and event removed from Google Calendar!')
    else:
        print('Permission denied!')
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
        slots = Slot.query.filter_by(slot_date=search_date).all()
    else:
        slots = Slot.query.all()
        
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
        excluded = request.form.getlist('exclude_days')  # e.g., ['saturday', 'sunday']

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
            day_name = current_date.strftime('%A').lower()  # e.g., "monday"
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
    excluded = request.form.getlist('excluded[]')  # Hidden input for excluded days

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

def add_event_to_calendar(slot):
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    print("Loading service account credentials...")
    credentials = service_account.Credentials.from_service_account_file(
        'google_credentials.json', scopes=SCOPES)
    print("Credentials loaded successfully. Building the Google Calendar service...")
    service = build('calendar', 'v3', credentials=credentials)

    start_dt = datetime.combine(slot.slot_date, slot.slot_start_time)
    end_dt = start_dt + timedelta(hours=1)
    print(f"Creating an event from {start_dt.isoformat()} to {end_dt.isoformat()}")

    event = {
        'summary': f'Lecture Recording: {slot.slot_date}',
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
    }
    print("Event details:", event)

    try:
        created_event = service.events().insert(calendarId='16d7113cfeb8be20173045a8dd418905d7e91da5f00f7238e95b5a8f4f25217c@group.calendar.google.com', body=event).execute()
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
        'google_credentials.json', scopes=SCOPES)
    service = build('calendar', 'v3', credentials=credentials)

    try:
        service.events().delete(calendarId='16d7113cfeb8be20173045a8dd418905d7e91da5f00f7238e95b5a8f4f25217c@group.calendar.google.com', eventId=event_id).execute()
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

if __name__ == '__main__':
    app.run(debug=True)
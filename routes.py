import os
import logging
import folium
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, CNGStation, EmergencyContact, SOSRequest
from helpers import get_traffic_data, get_optimal_route, get_nearby_cng_stations, format_duration
from twilio_service import send_multiple_sos_messages
from datetime import datetime

# Home page route
@app.route('/')
def index():
    return render_template('index.html')

# User registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role', 'user')  # Default to 'user'
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
            
        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(username=username, email=email, role=role)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error registering user: {str(e)}")
            flash('An error occurred during registration', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Validation
        if not username or not password:
            flash('Username and password are required', 'danger')
            return redirect(url_for('login'))
        
        # Find user
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            
            # Redirect based on role
            if user.is_owner():
                return redirect(url_for('owner_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
            return redirect(url_for('login'))
    
    return render_template('login.html')

# User logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# User dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# Traffic heatmap
@app.route('/traffic-heatmap', methods=['POST'])
def traffic_heatmap():
    latitude = float(request.form.get('latitude', 40.7128))  # Default to NYC
    longitude = float(request.form.get('longitude', -74.0060))
    
    # Get traffic data
    traffic_data = get_traffic_data(latitude, longitude)
    
    # Create a map centered at the given coordinates
    m = folium.Map(location=[latitude, longitude], zoom_start=13)
    
    # Add traffic data to the map (simplified for example)
    if 'trafficItems' in traffic_data and not isinstance(traffic_data.get('trafficItems'), list):
        for item in traffic_data.get('trafficItems', []):
            if 'location' in item:
                location = item['location']
                if 'geolocation' in location:
                    coords = location['geolocation']['coordinates']
                    severity = item.get('criticality', 0)
                    
                    # Color based on severity
                    color = 'green'
                    if severity > 3:
                        color = 'red'
                    elif severity > 1:
                        color = 'orange'
                    
                    folium.CircleMarker(
                        location=[coords[1], coords[0]],
                        radius=5 + (severity * 2),
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.6,
                        popup=item.get('description', 'Traffic incident')
                    ).add_to(m)
    
    # Convert map to HTML
    map_html = m._repr_html_()
    
    return jsonify({
        'map_html': map_html,
        'traffic_data': traffic_data
    })

# Route finder
@app.route('/find-route', methods=['POST'])
def find_route():
    start_lat = float(request.form.get('start_lat'))
    start_lng = float(request.form.get('start_lng'))
    end_lat = float(request.form.get('end_lat'))
    end_lng = float(request.form.get('end_lng'))
    transport_mode = request.form.get('transport_mode', 'driving-car')
    
    # Get optimal route
    route_data = get_optimal_route(
        [start_lng, start_lat],
        [end_lng, end_lat],
        transport_mode
    )
    
    if 'error' in route_data:
        return jsonify({
            'success': False,
            'error': route_data['error']
        })
    
    # Create a map
    m = folium.Map(location=[(start_lat + end_lat) / 2, (start_lng + end_lng) / 2], zoom_start=10)
    
    # Add markers for start and end points
    folium.Marker(
        [start_lat, start_lng],
        popup='Start',
        icon=folium.Icon(color='green', icon='play', prefix='fa')
    ).add_to(m)
    
    folium.Marker(
        [end_lat, end_lng],
        popup='End',
        icon=folium.Icon(color='red', icon='stop', prefix='fa')
    ).add_to(m)
    
    # Add the route to the map
    route_coords = []
    if 'route' in route_data and 'geometry' in route_data['route']:
        route_geometry = route_data['route']['geometry']
        if route_geometry['type'] == 'LineString':
            # LineString coordinates are in [longitude, latitude] format
            for coord in route_geometry['coordinates']:
                route_coords.append([coord[1], coord[0]])  # Convert to [lat, lng]
    
    if route_coords:
        folium.PolyLine(
            route_coords,
            color='blue',
            weight=5,
            opacity=0.7,
            popup=f"Distance: {route_data['distance']['formatted']}, Duration: {format_duration(route_data['duration']['total_seconds'])}"
        ).add_to(m)
    
    # Convert map to HTML
    map_html = m._repr_html_()
    
    return jsonify({
        'success': True,
        'map_html': map_html,
        'duration': route_data['duration'],
        'distance': route_data['distance']
    })

# CNG stations route
@app.route('/cng-stations')
def cng_stations():
    return render_template('cng_stations.html')

# API endpoint to get nearby CNG stations
@app.route('/api/nearby-cng-stations', methods=['POST'])
def api_nearby_cng_stations():
    latitude = float(request.form.get('latitude'))
    longitude = float(request.form.get('longitude'))
    radius = int(request.form.get('radius', 5000))
    
    stations = get_nearby_cng_stations(latitude, longitude, radius)
    
    if isinstance(stations, dict) and 'error' in stations:
        return jsonify({
            'success': False,
            'error': stations['error']
        })
    
    # Create a map
    m = folium.Map(location=[latitude, longitude], zoom_start=12)
    
    # Add user's position marker
    folium.Marker(
        [latitude, longitude],
        popup='Your Position',
        icon=folium.Icon(color='blue', icon='user', prefix='fa')
    ).add_to(m)
    
    # Add station markers
    for station in stations:
        # Choose color based on status
        color = 'green'
        if station['status'] == 'closed':
            color = 'red'
        elif station['status'] == 'maintenance':
            color = 'orange'
        
        # Format popup content
        popup_content = f"""
        <strong>{station['name']}</strong><br>
        Status: {station['status']}<br>
        Price: ₹{station['price']:.2f}/kg<br>
        Address: {station['address']}<br>
        Hours: {station['operating_hours']}<br>
        Distance: {station['distance']:.2f} meters
        """
        
        folium.Marker(
            [station['latitude'], station['longitude']],
            popup=folium.Popup(popup_content, max_width=300),
            icon=folium.Icon(color=color, icon='gas-pump', prefix='fa')
        ).add_to(m)
    
    # Convert map to HTML
    map_html = m._repr_html_()
    
    return jsonify({
        'success': True,
        'map_html': map_html,
        'stations': stations
    })

# Owner dashboard
@app.route('/owner-dashboard')
@login_required
def owner_dashboard():
    if not current_user.is_owner():
        flash('Access denied. You must be a station owner.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get the owner's stations
    stations = CNGStation.query.filter_by(owner_id=current_user.id).all()
    
    return render_template('owner_dashboard.html', stations=stations)

# Add CNG station
@app.route('/add-station', methods=['POST'])
@login_required
def add_station():
    if not current_user.is_owner():
        return jsonify({
            'success': False,
            'error': 'Access denied. You must be a station owner.'
        })
    
    name = request.form.get('name')
    latitude = float(request.form.get('latitude'))
    longitude = float(request.form.get('longitude'))
    address = request.form.get('address')
    status = request.form.get('status', 'operational')
    price = float(request.form.get('price', 0))
    operating_hours = request.form.get('operating_hours', '24/7')
    
    # Validation
    if not name or not latitude or not longitude:
        return jsonify({
            'success': False,
            'error': 'Name, latitude, and longitude are required.'
        })
    
    # Create new station
    new_station = CNGStation(
        name=name,
        latitude=latitude,
        longitude=longitude,
        address=address,
        status=status,
        price=price,
        operating_hours=operating_hours,
        owner_id=current_user.id
    )
    
    try:
        db.session.add(new_station)
        db.session.commit()
        return jsonify({
            'success': True,
            'station_id': new_station.id,
            'message': 'Station added successfully!'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding station: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })

# Update CNG station
@app.route('/update-station/<int:station_id>', methods=['POST'])
@login_required
def update_station(station_id):
    if not current_user.is_owner():
        return jsonify({
            'success': False,
            'error': 'Access denied. You must be a station owner.'
        })
    
    # Find the station
    station = CNGStation.query.get(station_id)
    
    if not station:
        return jsonify({
            'success': False,
            'error': 'Station not found.'
        })
    
    # Verify ownership
    if station.owner_id != current_user.id:
        return jsonify({
            'success': False,
            'error': 'Access denied. You do not own this station.'
        })
    
    # Update station details
    station.name = request.form.get('name', station.name)
    station.status = request.form.get('status', station.status)
    station.price = float(request.form.get('price', station.price))
    station.operating_hours = request.form.get('operating_hours', station.operating_hours)
    station.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Station updated successfully!'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error updating station: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })

# SOS page
@app.route('/sos')
@login_required
def sos():
    # Get user's emergency contacts
    contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
    return render_template('sos.html', contacts=contacts)

# Add emergency contact
@app.route('/add-emergency-contact', methods=['POST'])
@login_required
def add_emergency_contact():
    name = request.form.get('name')
    phone = request.form.get('phone')
    relationship = request.form.get('relationship', '')
    
    # Validation
    if not name or not phone:
        return jsonify({
            'success': False,
            'error': 'Name and phone are required.'
        })
    
    # Create new contact
    new_contact = EmergencyContact(
        name=name,
        phone=phone,
        relationship=relationship,
        user_id=current_user.id
    )
    
    try:
        db.session.add(new_contact)
        db.session.commit()
        return jsonify({
            'success': True,
            'contact_id': new_contact.id,
            'message': 'Emergency contact added successfully!'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding emergency contact: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })

# Send SOS alert
@app.route('/send-sos', methods=['POST'])
@login_required
def send_sos():
    latitude = float(request.form.get('latitude'))
    longitude = float(request.form.get('longitude'))
    message = request.form.get('message', '')
    
    # Get user's emergency contacts
    contacts = EmergencyContact.query.filter_by(user_id=current_user.id).all()
    
    if not contacts:
        return jsonify({
            'success': False,
            'error': 'No emergency contacts found. Please add at least one contact.'
        })
    
    # Create SOS request record
    sos_request = SOSRequest(
        user_id=current_user.id,
        latitude=latitude,
        longitude=longitude,
        message=message,
        status='active'
    )
    
    try:
        db.session.add(sos_request)
        db.session.commit()
        
        # Log emergency contacts before sending
        logging.info(f"Sending SOS to {len(contacts)} contacts for user {current_user.username}")
        for contact in contacts:
            logging.info(f"Contact: {contact.name}, Phone: {contact.phone}")
        
        # Send SOS messages to all contacts
        result = send_multiple_sos_messages(
            contacts,
            current_user.username,
            latitude,
            longitude,
            message
        )
        
        # Update SOS request status in DB based on result
        if result['success']:
            sos_request.status = 'sent'
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'SOS alerts sent successfully!',
                'results': result['results']
            })
        else:
            # Even if some failed, we still mark as partially sent
            sos_request.status = 'partial'
            db.session.commit()
            logging.error(f"SOS partial send failure: {result}")
            return jsonify({
                'success': False,
                'error': 'Some SOS alerts failed to send.',
                'results': result['results']
            })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error processing SOS request: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('index.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('index.html', error="Server error occurred"), 500

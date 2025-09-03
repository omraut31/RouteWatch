import os
import requests
import openrouteservice
import herepy
import logging
from datetime import datetime, timedelta

# API keys from environment
HERE_API_KEY = os.environ.get("HERE_API_KEY", "your_here_api_key")
ORS_API_KEY = os.environ.get("ORS_API_KEY", "your_ors_api_key")

# Initialize API clients
try:
    # OpenRouteService client
    ors_client = openrouteservice.Client(key=ORS_API_KEY)
    
    # HERE Map client
    here_traffic_api = herepy.TrafficApi(api_key=HERE_API_KEY)
    here_routing_api = herepy.RoutingApi(api_key=HERE_API_KEY)
except Exception as e:
    logging.error(f"Error initializing API clients: {str(e)}")

def get_traffic_data(latitude, longitude, radius=2000):
    """Get traffic data around a location using HERE Traffic API"""
    try:
        # Get traffic flow data
        response = here_traffic_api.traffic_flow_within_bbox(
            top_left=[latitude + 0.02, longitude - 0.02],
            bottom_right=[latitude - 0.02, longitude + 0.02]
        )
        
        if response.as_dict().get('trafficItems'):
            return response.as_dict()
        else:
            # If no traffic data, return empty structure
            return {"trafficItems": []}
    except Exception as e:
        logging.error(f"Error fetching traffic data: {str(e)}")
        return {"error": str(e)}

def get_optimal_route(start_coords, end_coords, transport_mode='driving-car'):
    """Get optimal route using OpenRouteService API"""
    try:
        # Request directions
        coords = [start_coords, end_coords]
        routes = ors_client.directions(
            coordinates=coords,
            profile=transport_mode,
            format='geojson',
            options={'avoid_features': ['tollways']},
            validate=False
        )
        
        # Extract route details
        if routes and 'features' in routes and len(routes['features']) > 0:
            route = routes['features'][0]
            properties = route['properties']
            
            # Calculate duration in hours, minutes, seconds
            duration_sec = properties['summary']['duration']
            hours = int(duration_sec // 3600)
            minutes = int((duration_sec % 3600) // 60)
            seconds = int(duration_sec % 60)
            
            # Calculate distance in kilometers
            distance_km = properties['summary']['distance'] / 1000
            
            return {
                'route': route,
                'duration': {
                    'hours': hours,
                    'minutes': minutes,
                    'seconds': seconds,
                    'total_seconds': duration_sec
                },
                'distance': {
                    'km': distance_km,
                    'formatted': f"{distance_km:.2f} km"
                }
            }
        else:
            return {"error": "No route found"}
    except Exception as e:
        logging.error(f"Error fetching optimal route: {str(e)}")
        return {"error": str(e)}

def get_nearby_cng_stations(latitude, longitude, radius=5000):
    """Get nearby CNG stations (simulated for now, would use actual API in production)"""
    # In a real implementation, this would call an actual CNG station API
    # For now, we'll use our database to retrieve stations
    from models import CNGStation
    from app import db
    import math
    
    try:
        # Find stations within the radius using a simple distance calculation
        # This is a simplified approach; in production, you'd use spatial queries
        stations = CNGStation.query.all()
        nearby_stations = []
        
        for station in stations:
            # Calculate distance using Haversine formula
            R = 6371e3  # Earth radius in meters
            φ1 = math.radians(latitude)
            φ2 = math.radians(station.latitude)
            Δφ = math.radians(station.latitude - latitude)
            Δλ = math.radians(station.longitude - longitude)
            
            a = math.sin(Δφ/2) * math.sin(Δφ/2) + \
                math.cos(φ1) * math.cos(φ2) * \
                math.sin(Δλ/2) * math.sin(Δλ/2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            
            distance = R * c
            
            if distance <= radius:
                nearby_stations.append({
                    'id': station.id,
                    'name': station.name,
                    'latitude': station.latitude,
                    'longitude': station.longitude,
                    'address': station.address,
                    'status': station.status,
                    'price': station.price,
                    'operating_hours': station.operating_hours,
                    'distance': distance
                })
        
        # Sort by distance
        nearby_stations.sort(key=lambda x: x['distance'])
        
        return nearby_stations
    except Exception as e:
        logging.error(f"Error fetching nearby CNG stations: {str(e)}")
        return {"error": str(e)}

def format_duration(seconds):
    """Format duration in seconds to hours, minutes, seconds string"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

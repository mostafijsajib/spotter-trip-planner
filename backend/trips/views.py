import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .hos_calculator import HOSCalculator


def get_route(start_coords, end_coords):
    """Get route from OpenRouteService (free)"""
    url = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}".format(
        start_coords[1], start_coords[0],
        end_coords[1], end_coords[0],
    )
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        route = data["routes"][0]
        distance_meters = route["distance"]
        distance_miles = distance_meters * 0.000621371
        waypoints = route["geometry"]["coordinates"]
        # OSRM returns [lng, lat] — flip to [lat, lng] for Leaflet
        waypoints = [[p[1], p[0]] for p in waypoints]
        return distance_miles, waypoints
    except Exception as e:
        return None, []


def geocode(location: str):
    """Geocode location using Nominatim (free)"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": location, "format": "json", "limit": 1}
    headers = {"User-Agent": "SpotterTripPlanner/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
        return None
    except Exception:
        return None


@api_view(["POST"])
def calculate_trip(request):
    data = request.data

    current_location = data.get("current_location", "")
    pickup_location = data.get("pickup_location", "")
    dropoff_location = data.get("dropoff_location", "")
    cycle_used_hours = float(data.get("cycle_used_hours", 0))

    # Validate
    if not all([current_location, pickup_location, dropoff_location]):
        return Response(
            {"error": "All location fields are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if cycle_used_hours < 0 or cycle_used_hours > 70:
        return Response(
            {"error": "Cycle used hours must be between 0 and 70."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Geocode locations
    current_coords = geocode(current_location)
    pickup_coords = geocode(pickup_location)
    dropoff_coords = geocode(dropoff_location)

    if not current_coords:
        return Response({"error": f"Could not find location: {current_location}"}, status=400)
    if not pickup_coords:
        return Response({"error": f"Could not find location: {pickup_location}"}, status=400)
    if not dropoff_coords:
        return Response({"error": f"Could not find location: {dropoff_location}"}, status=400)

    # Get routes
    distance_to_pickup, waypoints_to_pickup = get_route(current_coords, pickup_coords)
    distance_pickup_to_dropoff, waypoints_pickup_to_dropoff = get_route(pickup_coords, dropoff_coords)

    if distance_to_pickup is None or distance_pickup_to_dropoff is None:
        return Response({"error": "Could not calculate route."}, status=400)

    # Calculate HOS
    calculator = HOSCalculator()
    result = calculator.calculate_trip(
        current_location=current_location,
        pickup_location=pickup_location,
        dropoff_location=dropoff_location,
        cycle_used_hours=cycle_used_hours,
        distance_to_pickup=distance_to_pickup,
        distance_pickup_to_dropoff=distance_pickup_to_dropoff,
        waypoints_to_pickup=waypoints_to_pickup,
        waypoints_pickup_to_dropoff=waypoints_pickup_to_dropoff,
    )

    # Serialize stops
    stops_data = []
    for stop in result.stops:
        stops_data.append({
            "location": stop.location,
            "arrival_time": round(stop.arrival_time, 2),
            "departure_time": round(stop.departure_time, 2),
            "stop_type": stop.stop_type,
            "duration": round(stop.duration, 2),
        })

    # Serialize daily logs
    daily_logs_data = []
    for log in result.daily_logs:
        entries = []
        for entry in log.entries:
            entries.append({
                "start_time": round(entry.start_time, 2),
                "end_time": round(entry.end_time, 2),
                "status": entry.status,
                "location": entry.location,
            })
        daily_logs_data.append({
            "day": log.day,
            "date_offset": round(log.date_offset, 2),
            "entries": entries,
            "total_driving": log.total_driving,
            "total_on_duty": log.total_on_duty,
            "total_off_duty": log.total_off_duty,
        })

    return Response({
        "total_distance_miles": round(result.total_distance_miles, 1),
        "total_duration_hours": round(result.total_duration_hours, 2),
        "stops": stops_data,
        "daily_logs": daily_logs_data,
        "route_waypoints": result.route_waypoints,
        "coordinates": {
            "current": list(current_coords),
            "pickup": list(pickup_coords),
            "dropoff": list(dropoff_coords),
        }
    })

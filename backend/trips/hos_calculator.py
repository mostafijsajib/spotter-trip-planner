from dataclasses import dataclass, field
from typing import List


@dataclass
class Stop:
    location: str
    arrival_time: float      # hours from trip start
    departure_time: float
    stop_type: str           # 'pickup', 'dropoff', 'rest', 'fuel', 'break'
    duration: float          # hours


@dataclass
class LogEntry:
    start_time: float        # hours from trip start
    end_time: float
    status: str              # 'off_duty', 'driving', 'on_duty_not_driving'
    location: str


@dataclass
class DailyLog:
    day: int
    date_offset: float       # hours from trip start when day begins
    entries: List[LogEntry] = field(default_factory=list)
    total_driving: float = 0.0
    total_on_duty: float = 0.0
    total_off_duty: float = 0.0


@dataclass
class TripResult:
    total_distance_miles: float
    total_duration_hours: float
    stops: List[Stop]
    daily_logs: List[DailyLog]
    route_waypoints: list      # list of [lat, lng]


class HOSCalculator:
    # HOS Constants
    MAX_DRIVING_PER_DAY = 11.0       # hours
    MAX_WINDOW_PER_DAY = 14.0        # hours
    REQUIRED_OFF_DUTY = 10.0         # hours
    BREAK_AFTER_DRIVING = 8.0        # hours (need 30min break)
    BREAK_DURATION = 0.5             # hours
    MAX_CYCLE_HOURS = 70.0           # hours in 8 days
    FUEL_STOP_INTERVAL = 1000.0      # miles
    FUEL_STOP_DURATION = 0.5         # hours
    PICKUP_DROPOFF_DURATION = 1.0    # hours
    AVG_SPEED_MPH = 55.0             # average truck speed

    def calculate_trip(
        self,
        current_location: str,
        pickup_location: str,
        dropoff_location: str,
        cycle_used_hours: float,
        distance_to_pickup: float,
        distance_pickup_to_dropoff: float,
        waypoints_to_pickup: list,
        waypoints_pickup_to_dropoff: list,
    ) -> TripResult:

        total_distance = distance_to_pickup + distance_pickup_to_dropoff
        stops = []
        log_entries = []

        # State tracking
        current_time = 0.0          # hours from trip start
        driving_today = 0.0
        window_start = 0.0          # when today's 14hr window started
        driving_since_break = 0.0
        cycle_hours = cycle_used_hours
        current_location_name = current_location
        miles_since_fuel = 0.0

        # --- Helper: add a rest/break stop ---
        def add_rest(duration: float, stop_type: str, reason: str):
            nonlocal current_time, driving_today, window_start, driving_since_break
            stops.append(Stop(
                location=current_location_name,
                arrival_time=current_time,
                departure_time=current_time + duration,
                stop_type=stop_type,
                duration=duration,
            ))
            log_entries.append(LogEntry(
                start_time=current_time,
                end_time=current_time + duration,
                status='off_duty' if duration >= 1.0 else 'on_duty_not_driving',
                location=current_location_name,
            ))
            current_time += duration
            if duration >= self.REQUIRED_OFF_DUTY:
                driving_today = 0.0
                driving_since_break = 0.0
                window_start = current_time

        # --- Helper: drive a segment ---
        def drive_segment(miles: float, destination: str):
            nonlocal current_time, driving_today, driving_since_break
            nonlocal cycle_hours, miles_since_fuel, current_location_name

            remaining_miles = miles

            while remaining_miles > 0:
                # Check 30-min break needed
                if driving_since_break >= self.BREAK_AFTER_DRIVING:
                    add_rest(self.BREAK_DURATION, 'break', '30min break required')

                # Check 11hr driving limit
                if driving_today >= self.MAX_DRIVING_PER_DAY:
                    add_rest(self.REQUIRED_OFF_DUTY, 'rest', '10hr rest - driving limit')

                # Check 14hr window
                window_used = current_time - window_start
                if window_used >= self.MAX_WINDOW_PER_DAY:
                    add_rest(self.REQUIRED_OFF_DUTY, 'rest', '10hr rest - window limit')

                # Check cycle hours
                if cycle_hours >= self.MAX_CYCLE_HOURS:
                    add_rest(self.REQUIRED_OFF_DUTY, 'rest', '10hr rest - cycle limit')

                # Check fuel stop
                if miles_since_fuel >= self.FUEL_STOP_INTERVAL:
                    stops.append(Stop(
                        location=current_location_name,
                        arrival_time=current_time,
                        departure_time=current_time + self.FUEL_STOP_DURATION,
                        stop_type='fuel',
                        duration=self.FUEL_STOP_DURATION,
                    ))
                    log_entries.append(LogEntry(
                        start_time=current_time,
                        end_time=current_time + self.FUEL_STOP_DURATION,
                        status='on_duty_not_driving',
                        location=current_location_name,
                    ))
                    current_time += self.FUEL_STOP_DURATION
                    miles_since_fuel = 0.0

                # How many hours can we drive right now?
                hours_before_break = self.BREAK_AFTER_DRIVING - driving_since_break
                hours_before_daily_limit = self.MAX_DRIVING_PER_DAY - driving_today
                hours_before_window = self.MAX_WINDOW_PER_DAY - (current_time - window_start)
                hours_before_cycle = self.MAX_CYCLE_HOURS - cycle_hours

                max_drive_hours = min(
                    hours_before_break,
                    hours_before_daily_limit,
                    hours_before_window,
                    hours_before_cycle,
                )

                if max_drive_hours <= 0:
                    add_rest(self.REQUIRED_OFF_DUTY, 'rest', '10hr rest')
                    continue

                # Miles we can drive in max_drive_hours
                max_miles = max_drive_hours * self.AVG_SPEED_MPH
                miles_to_drive = min(remaining_miles, max_miles)
                hours_driven = miles_to_drive / self.AVG_SPEED_MPH

                log_entries.append(LogEntry(
                    start_time=current_time,
                    end_time=current_time + hours_driven,
                    status='driving',
                    location=current_location_name,
                ))

                current_time += hours_driven
                driving_today += hours_driven
                driving_since_break += hours_driven
                cycle_hours += hours_driven
                miles_since_fuel += miles_to_drive
                remaining_miles -= miles_to_drive

            current_location_name = destination

        # --- Execute trip ---

        # Drive to pickup
        drive_segment(distance_to_pickup, pickup_location)

        # Pickup stop (1 hour on duty)
        stops.append(Stop(
            location=pickup_location,
            arrival_time=current_time,
            departure_time=current_time + self.PICKUP_DROPOFF_DURATION,
            stop_type='pickup',
            duration=self.PICKUP_DROPOFF_DURATION,
        ))
        log_entries.append(LogEntry(
            start_time=current_time,
            end_time=current_time + self.PICKUP_DROPOFF_DURATION,
            status='on_duty_not_driving',
            location=pickup_location,
        ))
        current_time += self.PICKUP_DROPOFF_DURATION

        # Drive to dropoff
        drive_segment(distance_pickup_to_dropoff, dropoff_location)

        # Dropoff stop (1 hour on duty)
        stops.append(Stop(
            location=dropoff_location,
            arrival_time=current_time,
            departure_time=current_time + self.PICKUP_DROPOFF_DURATION,
            stop_type='dropoff',
            duration=self.PICKUP_DROPOFF_DURATION,
        ))
        log_entries.append(LogEntry(
            start_time=current_time,
            end_time=current_time + self.PICKUP_DROPOFF_DURATION,
            status='on_duty_not_driving',
            location=dropoff_location,
        ))
        current_time += self.PICKUP_DROPOFF_DURATION

        # --- Build daily logs ---
        daily_logs = self._build_daily_logs(log_entries)

        # Combine waypoints
        all_waypoints = waypoints_to_pickup + waypoints_pickup_to_dropoff

        return TripResult(
            total_distance_miles=total_distance,
            total_duration_hours=current_time,
            stops=stops,
            daily_logs=daily_logs,
            route_waypoints=all_waypoints,
        )

    def _build_daily_logs(self, log_entries: List[LogEntry]) -> List[DailyLog]:
        daily_logs = []
        day = 1
        day_start = 0.0
        day_end = 24.0

        while True:
            entries_today = []
            for entry in log_entries:
                # find entries that overlap with this day
                start = max(entry.start_time, day_start)
                end = min(entry.end_time, day_end)
                if end > start:
                    entries_today.append(LogEntry(
                        start_time=start - day_start,
                        end_time=end - day_start,
                        status=entry.status,
                        location=entry.location,
                    ))

            if not entries_today:
                break

            total_driving = sum(
                e.end_time - e.start_time
                for e in entries_today if e.status == 'driving'
            )
            total_on_duty = sum(
                e.end_time - e.start_time
                for e in entries_today if e.status == 'on_duty_not_driving'
            )
            total_off_duty = sum(
                e.end_time - e.start_time
                for e in entries_today if e.status == 'off_duty'
            )

            daily_logs.append(DailyLog(
                day=day,
                date_offset=day_start,
                entries=entries_today,
                total_driving=round(total_driving, 2),
                total_on_duty=round(total_on_duty, 2),
                total_off_duty=round(total_off_duty, 2),
            ))

            day += 1
            day_start += 24.0
            day_end += 24.0

            # Stop after all entries are covered
            max_time = max(e.end_time for e in log_entries)
            if day_start > max_time:
                break

        return daily_logs

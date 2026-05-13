import React, { useState } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, Polyline, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './index.css';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const stopColors = { pickup: '#22c55e', dropoff: '#ef4444', rest: '#3b82f6', break: '#f59e0b', fuel: '#8b5cf6' };
const stopIcons = { pickup: '📦', dropoff: '🏁', rest: '🛏️', break: '☕', fuel: '⛽' };

function createColoredIcon(color) {
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;background:${color};border:2px solid white;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,0.3);"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function formatHour(h) {
  const totalMin = Math.round(h * 60);
  const hrs = Math.floor(totalMin / 60) % 24;
  const mins = totalMin % 60;
  const ampm = hrs >= 12 ? 'PM' : 'AM';
  const displayHr = hrs % 12 || 12;
  return `${displayHr}:${mins.toString().padStart(2, '0')} ${ampm}`;
}

function ELDLog({ log }) {
  const rows = ['driving', 'on_duty_not_driving', 'off_duty'];
  const labels = { driving: 'Driving', on_duty_not_driving: 'On Duty', off_duty: 'Off Duty' };

  return (
    <div className="eld-log">
      <div className="eld-log-header">
        <span className="day-title">Day {log.day}</span>
        <span className="day-totals">Drive: {log.total_driving}h | On Duty: {log.total_on_duty}h | Off: {log.total_off_duty}h</span>
      </div>
      <div className="eld-grid">
        <div className="eld-grid-header">
          <div className="eld-grid-label"></div>
          <div className="eld-grid-hours">
            {[0, 6, 12, 18, 24].map(h => (
              <span key={h}>{h === 0 ? 'Mid' : h === 24 ? 'Mid' : `${h > 12 ? h - 12 : h}${h >= 12 ? 'P' : 'A'}`}</span>
            ))}
          </div>
        </div>
        {rows.map(status => (
          <div key={status} className="eld-row">
            <div className="eld-row-label">{labels[status]}</div>
            <div className="eld-row-track">
              {log.entries.filter(e => e.status === status).map((e, i) => (
                <div key={i} className={`eld-segment ${status}`}
                  style={{ left: `${(e.start_time / 24) * 100}%`, width: `${((e.end_time - e.start_time) / 24) * 100}%` }}
                  title={`${formatHour(e.start_time)} - ${formatHour(e.end_time)}`}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="eld-legend">
        <div className="legend-item"><div className="legend-dot driving" /><span>Driving</span></div>
        <div className="legend-item"><div className="legend-dot on_duty" /><span>On Duty</span></div>
        <div className="legend-item"><div className="legend-dot off_duty" /><span>Off Duty</span></div>
      </div>
    </div>
  );
}

export default function App() {
  const [form, setForm] = useState({ current_location: '', pickup_location: '', dropoff_location: '', cycle_used_hours: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const backendUrl = "https://trip-api.mrsajib.com";

  const handleSubmit = async e => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await axios.post(`${backendUrl}/api/trips/calculate/`, {
        ...form,
        cycle_used_hours: parseFloat(form.cycle_used_hours) || 0,
      });
      setResult(res.data);
    } catch (err) {
      setError(err.response?.data?.error || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const mapCenter = result ? result.coordinates.current : [39.5, -90.0];

  return (
    <div className="app">
      <div className="header">
        <div>
          <h1>🚛 Spotter Trip Planner</h1>
          <p>HOS-compliant route planning with ELD log generation</p>
        </div>
      </div>
      <div className="main">
        <div className="sidebar">
          <div className="form-section">
            <h2>Trip Details</h2>
            <form onSubmit={handleSubmit}>
              {['current_location', 'pickup_location', 'dropoff_location'].map(field => (
                <div className="form-group" key={field}>
                  <label>{field.replace(/_/g, ' ')}</label>
                  <input name={field} value={form[field]} onChange={e => setForm({ ...form, [field]: e.target.value })}
                    placeholder={field === 'current_location' ? 'e.g. Chicago, IL' : field === 'pickup_location' ? 'e.g. Indianapolis, IN' : 'e.g. Nashville, TN'} required />
                </div>
              ))}
              <div className="form-group">
                <label>Current Cycle Used (Hours)</label>
                <input type="number" min="0" max="70" step="0.5" value={form.cycle_used_hours}
                  onChange={e => setForm({ ...form, cycle_used_hours: e.target.value })} placeholder="e.g. 20" required />
              </div>
              {error && <div className="error-msg">{error}</div>}
              <button type="submit" className="submit-btn" disabled={loading}>
                {loading ? 'Calculating...' : 'Calculate Trip'}
              </button>
            </form>
          </div>

          {loading && <div className="loading"><div className="spinner" />Calculating route...</div>}

          {result && !loading && (
            <>
              <div className="stats-section">
                {[
                  { label: 'Distance', value: result.total_distance_miles.toFixed(0), unit: 'miles' },
                  { label: 'Duration', value: result.total_duration_hours.toFixed(1), unit: 'hours' },
                  { label: 'Stops', value: result.stops.length, unit: 'total' },
                  { label: 'Log Days', value: result.daily_logs.length, unit: 'days' },
                ].map(s => (
                  <div className="stat-card" key={s.label}>
                    <div className="label">{s.label}</div>
                    <div className="value">{s.value}</div>
                    <div className="unit">{s.unit}</div>
                  </div>
                ))}
              </div>

              <div className="stops-section">
                <h2>Route Stops</h2>
                {result.stops.map((stop, i) => (
                  <div key={i} className={`stop-item ${stop.stop_type}`}>
                    <div className="stop-icon">{stopIcons[stop.stop_type] || '📍'}</div>
                    <div className="stop-info">
                      <div className="stop-type">{stop.stop_type.replace('_', ' ')}</div>
                      <div className="stop-location">{stop.location}</div>
                      <div className="stop-time">{formatHour(stop.arrival_time)} – {formatHour(stop.departure_time)} ({stop.duration}h)</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="logs-section">
                <h2>ELD Daily Logs</h2>
                {result.daily_logs.map(log => <ELDLog key={log.day} log={log} />)}
              </div>
            </>
          )}

          {!result && !loading && (
            <div className="empty-state">
              <div className="icon">🗺️</div>
              <p>Enter trip details above to generate<br />an HOS-compliant route plan</p>
            </div>
          )}
        </div>

        <div className="map-container">
          <MapContainer center={mapCenter} zoom={result ? 6 : 5} className="leaflet-map" key={result ? 'result' : 'empty'}>
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; OpenStreetMap contributors' />
            {result && (
              <>
                <Polyline positions={result.route_waypoints} color="#1a3c5e" weight={3} opacity={0.8} />
                <Marker position={result.coordinates.current}><Popup>📍 Current Location</Popup></Marker>
                {result.stops.filter(s => s.stop_type === 'pickup' || s.stop_type === 'dropoff').map((stop, i) => (
                  <Marker key={i}
                    position={stop.stop_type === 'pickup' ? result.coordinates.pickup : result.coordinates.dropoff}
                    icon={createColoredIcon(stopColors[stop.stop_type])}>
                    <Popup><strong>{stopIcons[stop.stop_type]} {stop.stop_type.toUpperCase()}</strong><br />{stop.location}<br />{formatHour(stop.arrival_time)} – {formatHour(stop.departure_time)}</Popup>
                  </Marker>
                ))}
              </>
            )}
          </MapContainer>
        </div>
      </div>
    </div>
  );
}
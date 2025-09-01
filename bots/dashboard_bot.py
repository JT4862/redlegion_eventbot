from flask import Flask, render_template, redirect
import psycopg2
import os
from datetime import timedelta

app = Flask(__name__, template_folder='/opt/render/project/src/templates')

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def format_duration(seconds):
    td = timedelta(seconds=float(seconds))
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

@app.route('/')
def index():
    return redirect('/dashboard', code=302)

@app.route('/dashboard')
def dashboard():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            SELECT e.event_name, e.start_time, e.end_time, p.username, p.duration
            FROM events e
            JOIN participation p ON e.channel_id = p.channel_id
            WHERE e.end_time IS NOT NULL
            ORDER BY e.start_time DESC
        ''')
        data = c.fetchall()
        conn.close()

        # Format data for display
        events = []
        for row in data:
            event_name, start_time, end_time, username, duration = row
            events.append({
                'event_name': event_name,
                'start_time': start_time,
                'end_time': end_time or 'N/A',
                'username': username or 'Unknown',
                'duration': format_duration(duration)
            })
        return render_template('dashboard.html', events=events)
    except psycopg2.OperationalError as e:
        print(f"Database error: {e}")
        return render_template('dashboard.html', events=[])

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
from flask import Flask, render_template, redirect
import psycopg2
import os
import datetime

app = Flask(__name__, template_folder='/opt/render/project/src/templates')

@app.route('/')
def index():
    return redirect('/dashboard', code=302)

@app.route('/dashboard')
def dashboard():
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        c = conn.cursor()
        current_month = datetime.datetime.now().strftime("%B-%Y")
        # Fetch events for the current month
        c.execute("SELECT channel_id, event_name, start_time FROM events WHERE to_char(to_timestamp(start_time, 'YYYY-MM-DD HH24:MI:SS'), 'Month-YYYY') = %s", (current_month,))
        events = c.fetchall()
        # Fetch participation data
        c.execute("SELECT channel_id, member_id, duration FROM participation")
        participation = c.fetchall()
        conn.close()

        # Aggregate participation data by user
        user_totals = {}
        for event in events:
            channel_id, _, start_time = event
            if datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").strftime("%B-%Y") != current_month:
                continue
            for p in participation:
                if p[0] == channel_id:
                    member_id, duration = p[1], p[2]
                    user_totals[member_id] = user_totals.get(member_id, 0) + duration

        labels = []
        values = []
        for member_id, total in sorted(user_totals.items(), key=lambda x: x[1], reverse=True):
            try:
                labels.append(f"User_{member_id[-4:]}")  # Placeholder for display name
                values.append(total / 60)  # Convert seconds to minutes
            except Exception:
                continue
    except psycopg2.OperationalError as e:
        print(f"Database error: {e}")
        labels, values = [], []

    return render_template('dashboard.html', labels=labels, values=values, month=current_month)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port)